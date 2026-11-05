"""Bridge from presence intents to Ground messages. No dog or drone socket."""

from patrol.bridge.messages import command_message, proposal_message

__all__ = ["command_message", "proposal_message"]
