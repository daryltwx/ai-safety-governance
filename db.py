"""
SQLAlchemy schema + session factory for the Postgres+pgvector database.

Real infrastructure, always-synthetic data -- see seed_data.py. This
database replaces two things that used to be hardcoded in app.py:
CITIZEN_RECORDS (a two-entry dict) and DOCS (a six-entry list with
keyword-match "retrieval"). Both become real tables; DOCS additionally
gets a pgvector embedding column so search_docs() can do real cosine-
similarity search instead of keyword overlap.

Nothing in here is PII-sensitive by construction: every row in this
database is Faker-generated. The NRIC format, schema shape, and query
patterns are real; the people are not.
"""
from sqlalchemy import create_engine, text, Column, String, Date, Numeric, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from pgvector.sqlalchemy import Vector
from langchain_ollama import OllamaEmbeddings

import config

engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

# nomic-embed-text's output size (config.EMBEDDING_MODEL's default) --
# confirmed via a live call to Ollama's /api/embed, not assumed. If
# EMBEDDING_MODEL is swapped to a model with a different output size,
# this column width needs to change too (and the table re-seeded).
EMBEDDING_DIM = 768

# nomic-embed-text is instruction-tuned/asymmetric: it expects a
# "search_document: " / "search_query: " task prefix on the text it
# embeds, not just the raw text. Confirmed this isn't cosmetic -- without
# it, a live test query ("How much money can I get back for my doctor
# visits?") ranked the obviously-correct document (POL-014, outpatient
# subsidy) 9th of 16, with all 16 scores packed into a narrow,
# low-discrimination band. With the prefixes applied consistently on
# both sides, it ranks 1st (see docs/2026-10-06-real-database-and-rag.md
# for the before/after). Centralized here, not duplicated in seed_data.py
# and app.py separately, specifically so indexing and querying can't
# silently drift onto inconsistent conventions.
_embedder = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=config.OLLAMA_URL)


def embed_documents(texts: list) -> list:
    return _embedder.embed_documents([f"search_document: {t}" for t in texts])


def embed_query(text_: str) -> list:
    return _embedder.embed_query(f"search_query: {text_}")


class Citizen(Base):
    __tablename__ = "citizens"

    nric = Column(String(9), primary_key=True)
    name = Column(String, nullable=False)
    dob = Column(Date, nullable=False)
    medisave_balance = Column(Numeric(10, 2), nullable=False)
    subsidy_tier = Column(String, nullable=False)

    claims = relationship("Claim", back_populates="citizen", order_by="Claim.claim_date")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)
    citizen_nric = Column(String(9), ForeignKey("citizens.nric"), nullable=False, index=True)
    policy_ref = Column(String, nullable=False)   # e.g. "POL-014" -- matches PolicyDocument.doc_id
    claim_type = Column(String, nullable=False)   # e.g. "outpatient"
    claim_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    subsidised = Column(Boolean, nullable=False, default=True)

    citizen = relationship("Citizen", back_populates="claims")

    def display(self) -> str:
        """Render in the same shape the rest of the app (mask_record(),
        the system prompt's expectations) was already built around when
        claims were a flat list of strings -- keeps the DB migration from
        requiring changes to the tokenization/masking code downstream."""
        status = "subsidised" if self.subsidised else "not subsidised"
        return f"{self.policy_ref} {self.claim_type} claim, {self.claim_date.isoformat()}, ${self.amount} {status}"


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id = Column(Integer, primary_key=True)
    doc_id = Column(String, nullable=False, unique=True)   # e.g. "POL-014"
    title = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)


def init_db():
    """Create the vector extension (if missing) and all tables. Safe to
    call repeatedly -- CREATE EXTENSION IF NOT EXISTS / create_all() are
    both idempotent."""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine)
