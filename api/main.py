import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent.errors import AIServiceUnavailableError
from agent.orchestrator import HybridOrchestrator
from api.security import GENERIC_INTERNAL_ERROR, sanitize_orchestrator_result

logger = logging.getLogger(__name__)

orchestrator: HybridOrchestrator | None = None

MAX_QUESTION_LENGTH = 2000


@asynccontextmanager
async def lifespan(_: FastAPI):
    global orchestrator
    orchestrator = HybridOrchestrator()
    yield
    if orchestrator is not None:
        orchestrator.close()


app = FastAPI(title="Enterprise Knowledge Graph Agent", lifespan=lifespan)


class Question(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_QUESTION_LENGTH)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": GENERIC_INTERNAL_ERROR})


@app.post("/ask")
def ask(question: Question):
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        result = orchestrator.answer(question.text)
        return sanitize_orchestrator_result(result)
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to process /ask request")
        raise HTTPException(status_code=500, detail=GENERIC_INTERNAL_ERROR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)
