import logging
import sys
import os

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import upload as upload_router
from .routers import qa as qa_router
from .routers import stats as stats_router
from .routers import search as search_router
from .routers import chat as chat_router
from .routers import rank as rank_router
from .routers import visualization as visualization_router
from .utils.vector_store import VectorStore
from .services.qa_engine import QAEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app_debug.log", mode="a"),
    ],
)

# Create logger for this module
logger = logging.getLogger(__name__)

# Create the FastAPI app
def create_app() -> FastAPI:
    app = FastAPI(
        title="Statistical Hypothesis Testing Assistant",
        description=(
            "Upload research PDFs for Q&A and CSV datasets for intelligent "
            "statistical analysis. The LLM automatically selects and runs the "
            "most appropriate statistical test for your question."
        ),
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialise shared singletons
    store = VectorStore()
    engine = QAEngine(store)

    upload_router.set_vector_store(store)
    qa_router.set_engine(engine)

    # Register routers
    app.include_router(upload_router.router, prefix="/upload", tags=["Upload"])
    app.include_router(qa_router.router, prefix="/qa", tags=["Q&A"])
    app.include_router(stats_router.router, prefix="/stats", tags=["Statistics"])
    app.include_router(search_router.router, prefix="/search", tags=["Search"])
    app.include_router(chat_router.router, prefix="/chat", tags=["Chat"])
    app.include_router(rank_router.router, prefix="/rank", tags=["Rank"])
    app.include_router(visualization_router.router, prefix="/visualization", tags=["Visualization"])

    @app.get("/health")
    def health():
        return {
            "status": "ok"
        }

    logger.info("App created and routes registered")
    return app


app = create_app()
