"""Jev request shapes and answer parsing, with a fake HTTPS connection. No network."""

import json
import os
import socket
import unittest
from unittest import mock

from patrol.drone import jev


class FakeResponse:
    def __init__(self, status: int, body: dict | str) -> None:
        self.status = status
        self._body = body if isinstance(body, str) else json.dumps(body)

    def read(self) -> bytes:
        return self._body.encode()


class FakeConnection:
    def __init__(self, replies: list) -> None:
        self.replies = replies
        self.sent: list[dict] = []
        self.closed = False

    def request(self, method, path, body=None, headers=None) -> None:
        self.sent.append({"method": method, "path": path, "body": json.loads(body), "headers": headers})
        if isinstance(self.replies[0], Exception):
            raise self.replies.pop(0)

    def getresponse(self):
        return self.replies.pop(0)

    def close(self) -> None:
        self.closed = True


def guide_answers(blocked=0.1, steer="straight", person=0.0) -> dict:
    return {
        "blocked": {"type": "noul", "noul": blocked},
        "steer": {"type": "choice", "choice": steer, "confidence": 0.8, "probabilities": {}},
        "person": {"type": "noul", "noul": person},
    }


class RequestTests(unittest.TestCase):
    def test_guide_sends_one_image_and_three_typed_questions(self) -> None:
        body = jev.guide_request("AAAA", 100)
        self.assertEqual(body["model"], "typesafe/jev-1.14")
        images = [part for part in body["state"] if isinstance(part, dict)]
        self.assertEqual(images, [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}])
        kinds = {name: question["type"] for name, question in body["questions"].items()}
        self.assertEqual(kinds, {"blocked": "noul", "steer": "choice", "person": "noul"})
        self.assertEqual(set(body["questions"]["steer"]["criteria"]), {"left", "straight", "right"})

    def test_scan_labels_every_photo_and_offers_stay(self) -> None:
        body = jev.scan_request([(0, "A"), (90, "B"), (180, "C"), (270, "D")], back=180, height_cm=100)
        texts = [part for part in body["state"] if isinstance(part, str)]
        self.assertIn("Photo h090:", texts)
        self.assertTrue(any("h180 looks back" in text for text in texts))
        self.assertEqual(sum(1 for part in body["state"] if isinstance(part, dict)), 4)
        for label in ("h000", "h090", "h180", "h270"):
            self.assertEqual(body["questions"][f"blocked_{label}"]["type"], "noul")
            self.assertEqual(body["questions"][f"room_{label}"]["type"], "score")
            self.assertEqual(body["questions"][f"person_{label}"]["type"], "noul")
        self.assertEqual(set(body["questions"]["heading"]["criteria"]), {"h000", "h090", "h180", "h270", "stay"})

    def test_frames_are_resized_jpegs(self) -> None:
        from PIL import Image
        import base64
        import io

        b64 = jev.encode_frame(Image.new("RGB", (960, 720), "gray"))
        image = Image.open(io.BytesIO(base64.b64decode(b64)))
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(image.size, (640, 480))


class ParseTests(unittest.TestCase):
    def test_guide_parses(self) -> None:
        guide = jev.parse_guide(guide_answers(0.7, "left", 0.2), 0.4)
        self.assertEqual((guide.blocked, guide.steer, guide.person), (0.7, "left", 0.2))

    def test_wrong_types_are_errors_not_defaults(self) -> None:
        bad = guide_answers()
        bad["blocked"] = {"type": "score", "score": 0.1}
        with self.assertRaises(jev.JevError):
            jev.parse_guide(bad, 0.1)
        missing = guide_answers()
        del missing["person"]
        with self.assertRaises(jev.JevError):
            jev.parse_guide(missing, 0.1)
        odd = guide_answers(steer="up")
        with self.assertRaises(jev.JevError):
            jev.parse_guide(odd, 0.1)

    def test_room_rounds_down(self) -> None:
        self.assertEqual(jev.room_meters(0.0), 0.3)
        self.assertEqual(jev.room_meters(1.7), 1.0)
        self.assertEqual(jev.room_meters(2.99), 2.0)
        self.assertEqual(jev.room_meters(3.0), 3.0)

    def test_scan_parses_and_maps_the_pick_back_to_degrees(self) -> None:
        answers = {"heading": {"type": "choice", "choice": "h090", "confidence": 0.7}}
        for label in ("h000", "h090"):
            answers[f"blocked_{label}"] = {"type": "noul", "noul": 0.2}
            answers[f"room_{label}"] = {"type": "score", "score": 2.4}
            answers[f"person_{label}"] = {"type": "noul", "noul": 0.0}
        scan = jev.parse_scan(answers, [0, 90], 0.6)
        self.assertEqual(scan.choice, 90)
        self.assertEqual(scan.judgments[0].room_m, 2.0)
        answers["heading"]["choice"] = "stay"
        self.assertIsNone(jev.parse_scan(answers, [0, 90], 0.6).choice)

    def test_box_parses(self) -> None:
        box = jev.parse_box({
            "person": {"type": "noul", "noul": 0.9},
            "where": {"type": "box", "box": {"top": 0.2, "bottom": 0.9, "left": 0.6, "right": 0.8}, "confidence": 0.8},
        })
        self.assertAlmostEqual(box.center_x, 0.7)


class ClientTests(unittest.TestCase):
    def test_posts_to_openrouter_with_the_key_and_reuses_the_connection(self) -> None:
        conn = FakeConnection([FakeResponse(200, {"answers": guide_answers()}), FakeResponse(200, {"answers": guide_answers(0.9)})])
        made = []
        client = jev.JevClient("sk-test", connection_factory=lambda: made.append(1) or conn)
        self.assertEqual(client.guide("AAAA").blocked, 0.1)
        self.assertEqual(client.guide("AAAA").blocked, 0.9)
        self.assertEqual(len(made), 1)
        self.assertEqual(conn.sent[0]["path"], "/api/alpha/decisions")
        self.assertEqual(conn.sent[0]["headers"]["Authorization"], "Bearer sk-test")

    def test_http_error_is_an_error(self) -> None:
        conn = FakeConnection([FakeResponse(402, "no credit")])
        client = jev.JevClient("k", connection_factory=lambda: conn)
        with self.assertRaises(jev.JevError):
            client.guide("AAAA")

    def test_timeout_retries_once_then_fails(self) -> None:
        conn = FakeConnection([socket.timeout("slow"), socket.timeout("slow")])
        client = jev.JevClient("k", connection_factory=lambda: conn)
        with self.assertRaises(jev.JevError):
            client.guide("AAAA")

    def test_dropped_keepalive_reconnects(self) -> None:
        conns = [FakeConnection([ConnectionResetError("gone")]), FakeConnection([FakeResponse(200, {"answers": guide_answers()})])]
        client = jev.JevClient("k", connection_factory=lambda: conns.pop(0))
        self.assertEqual(client.guide("AAAA").steer, "straight")

    def test_failed_scan_reads_every_heading_blocked(self) -> None:
        conn = FakeConnection([FakeResponse(500, "boom")])
        client = jev.JevClient("k", connection_factory=lambda: conn)
        scan = client.scan([(0, "A"), (90, "B")])
        self.assertIsNone(scan.choice)
        self.assertEqual({j.blocked for j in scan.judgments.values()}, {1.0})

    def test_key_comes_from_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": " sk-env "}):
            self.assertEqual(jev.api_key(), "sk-env")


if __name__ == "__main__":
    unittest.main()
