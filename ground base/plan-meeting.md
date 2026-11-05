# Ground plan after the team meeting

This file is the working plan from the 5 November 2026 meeting, read against the Ground repo as it exists now. It does not replace [plan.md](plan.md). That older build specification stays unchanged.

No code is changed by this document. The Wi-Fi direction algorithm is not chosen here.

## 1. What the system does

A camera on the drone sees something worth checking. The dog is sent immediately, so it is already moving while the picture is still being judged. The drone keeps emitting its Wi-Fi beacon. A localization step, taken later from a public algorithm, turns those readings into one point: where the drone is. That point is the dog's next goal.

The dog walks to that point with its own obstacle avoidance. If a wall is between the dog and the point, the dog goes around it. Ground does not plan that path. When the person is inside the dog's forward camera, the Wi-Fi point is no longer needed. The camera is what identifies the person.

The drone can then follow the dog. Landing is on the dog's back. The dog's front camera cannot see the top of its own body, so the drone uses its downward camera and a QR code placed on the dog. A black-and-white QR on a black-and-white camera is acceptable.

Ground receives images from both cameras, gives them to one AI context, and gets back a description of the scene. If that context says the scene is safe, Ground calls land. The drone then runs its own landing. If the context says it is not safe, Ground does not call land.

## 2. Who owns what

Four trees stay separate. Ground is this repo. The drone, the dog, and the AI each stay in their own tree. WebRTC stays the link. MQTT is not part of this plan.

A public function is one Ground is allowed to call. A private function is the work inside that call. Ground does not see it and does not reimplement it.

| Call Ground may make | Who implements it | What Ground does not do |
| --- | --- | --- |
| `find_drone` | Dog | Bearing math, obstacle avoidance, the path around a wall |
| `return_home` | Dog | The route back |
| Start patrol (takeoff and search) | Drone | How the search is flown |
| Follow the dog | Drone | How the follow is flown |
| `land` | Drone | QR reading and the downward-camera landing |

`find_drone` is the public name that contains the private walker. Ground says "go find the drone" and waits. The point from the Wi-Fi algorithm is the input to that call. Ground stores the point. It does not compute it.

Inside the dog, once the person is in the forward camera, signal-following ends and image frames start flowing back. Ground sends those frames on. It does not decide the scene by itself.

## 3. What this repo already does

The live path is Ethernet WebRTC to the dog at `192.168.123.161:8081` from this laptop at `192.168.123.222`. The Mission page can check that cable, run a four-direction developer test, run the simulated happy-path with one live dog step, and show the dog camera and a developer LiDAR view.

The only motion Ground sends today is `move_local`: one body-frame velocity for a fraction of a second. The dog package accepts or refuses that step. The happy-path drone, pictures, and RSSI are scripts. Real Grok is refused until a real vision transport exists. Contracts already say obstacle planning and SLAM belong to the dog, and that Ground only selects among safe candidates the dog has published.

The dog commands the contracts know are `approach`, `move_local`, and `halt`. The drone commands include `reposition`, `track_step`, hover, and land. There is no `find_drone` and no `return_home`.

## 4. What the older plan.md decided, and what the meeting changes

[plan.md](plan.md) is the earlier dog-first specification. The meeting changes the operating picture. The old file stays as the record of that specification.

| Question | plan.md | This meeting |
| --- | --- | --- |
| Who sees the intruder first? | A phone or fixed camera. The dog goes to a named zone. | The drone. The dog is sent at once. |
| How does the dog know where to go? | A short calibrated route. RSSI homing is out of scope. | A point from the drone's Wi-Fi, then the dog camera when the person is in view. |
| Who avoids obstacles? | The dog, on its own route. | The dog, inside `find_drone`. Ground does not plan it. |
| Where does the drone land? | A cleared floor patch. A person retrieves it. | On the dog, after the AI context says it is safe, using the downward camera and a QR code. |
| What the operator presses | A local terminal: incident, status, halt, arrival, logs. | Two buttons: Start patrol and Stop patrol. LiDAR stays a developer view. |

## 5. Work this implies, still not started

1. Agree the public names and the JSON for `find_drone` and `return_home` with the dog repo, and for start-patrol, follow, and land with the drone repo. Do that before changing the rehearsal command. Today's examples only know the actions in section 3.

2. Leave the Wi-Fi algorithm unnamed. When a public repo is chosen, its output is one point in the dog's map. That point is the argument to `find_drone`.

3. Keep `move_local` as the cable test. The direction buttons and the short demo step stay for that. Start patrol does not send a velocity. It calls `find_drone` once that hook exists.

4. Pass drone frames and dog frames through Ground into one AI context. Ground keeps the replies as one situation: nothing seen, intruder seen, intruder in the dog camera, safe to land, or not safe. The AI describes the scene.

5. Put that result in front of landing. Stop patrol, or "the person has been handled," asks the context if landing is safe. Only a safe result calls `land`. The drone reads the QR. Ground does not.

6. Add Start patrol and Stop patrol on the Mission page, wired to those calls. Stop patrol sends the dog to the drone even when nobody is there, so the drone can land. LiDAR and the raw dog camera stay on the developer view. A later user screen can hide LiDAR. A chatbot, if it is added, may call only those two actions.

7. Do not merge the dog or drone trees into this repo, and do not switch the link to MQTT.
