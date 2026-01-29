from dataclasses import dataclass


@dataclass
class Track:
    id: str
    title: str
    audio_url: str
    duration: float | None = None
    artist: str | None = None
    image_url: str | None = None

    def __str__(self) -> str:
        if self.artist:
            return f"{self.title} - {self.artist}"
        return self.title
