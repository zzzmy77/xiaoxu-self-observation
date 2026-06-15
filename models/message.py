"""Message model."""
from datetime import datetime, timezone
from app import db
from utils.timezone import iso_utc


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user / assistant / system
    content = db.Column(db.Text, nullable=False)
    structured_meta = db.Column(db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "structured_meta": self.structured_meta,
            "created_at": iso_utc(self.created_at),
        }
