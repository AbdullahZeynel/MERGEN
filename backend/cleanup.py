"""One-shot cleanup invoked by the VPS systemd timer."""
from backend.live_store import LiveSettings, LiveStore


if __name__ == "__main__":
    print(LiveStore(LiveSettings.from_env()).cleanup())
