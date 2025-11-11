import uuid

from sqlalchemy import ARRAY, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    files_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    files: Mapped[list["File"]] = relationship("File", back_populates="user")
    requests: Mapped[list["Request"]] = relationship("Request", back_populates="user")


class File(Base):
    __tablename__ = "files"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_id_int: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=False
    )
    complexity: Mapped[int] = mapped_column(Integer, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="files")
    requests: Mapped[list["Request"]] = relationship("Request", back_populates="file")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.file_id"), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="requests")
    file: Mapped["File"] = relationship("File", back_populates="requests")
