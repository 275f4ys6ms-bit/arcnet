import json
import os

from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import noise_cancellation, openai, silero

from visual_schema import expand

CANVAS_WS = os.getenv("CANVAS_WS", "ws://localhost:8000/ws-agent")

INSTRUCTIONS = (
    "You are a live AI visual tutor. Explain clearly while controlling a live 2D "
    "vector canvas. Before narrating a visual element, call update_visual_canvas. "
    "Use short stable snake_case ids and reuse ids for the same element. "
    "Supported actions are draw, highlight, erase, and animate."
)


async def send_to_canvas(command: dict):
    import websockets
    async with websockets.connect(CANVAS_WS) as websocket:
        await websocket.send(json.dumps({"type": "scene", "cmd": command}))


class TutorAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)

    @agents.function_tool
    async def update_visual_canvas(self, action: str, object: str, attributes: str = "") -> str:
        """Update the canvas before narrating the visual element."""
        command = expand(action.strip().lower(), object.strip().lower().replace(" ", "_"), attributes)
        await send_to_canvas(command)
        return "ok"


async def entrypoint(context: agents.JobContext):
    await context.connect()
    session = AgentSession(llm=openai.realtime.RealtimeModel(voice=os.getenv("OPENAI_VOICE", "ash")), vad=silero.VAD.load())
    await session.start(room=context.room, agent=TutorAgent(), room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()))
    await session.generate_reply(instructions="Greet the learner and ask what topic they would like explained with live visuals.")


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
