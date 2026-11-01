"""RFC 9457 problem details for every error response.

``code`` is machine-readable; ``issues`` carries per-field problems with a
``path`` into the mission config so the frontend can focus the field.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from simcore.mission import Issue
from simcore.mission.validation import format_path

PROBLEM_JSON = "application/problem+json"


class Problem(BaseModel):
    type: str = Field(default="about:blank", description="URI identifying the problem type.")
    title: str = Field(description="Short summary of the problem type.")
    status: int = Field(description="HTTP status code.")
    detail: str | None = Field(default=None, description="Explanation of this occurrence.")
    code: str = Field(description="Machine-readable problem code.")
    issues: list[Issue] = Field(default_factory=list, description="Per-field problems, if any.")


class ApiProblem(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        issues: list[Issue] | None = None,
    ) -> None:
        self.problem = Problem(
            status=status, code=code, title=title, detail=detail, issues=issues or []
        )


def _response(problem: Problem) -> JSONResponse:
    return JSONResponse(problem.model_dump(), status_code=problem.status, media_type=PROBLEM_JSON)


def _strip_location(loc: tuple[Any, ...]) -> list[int | str]:
    # FastAPI prefixes "body"/"query"/"path"; the UI wants the config path.
    parts = list(loc)
    if parts and parts[0] in {"body", "query", "path"}:
        parts = parts[1:]
    return parts


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def _api_problem(_: Request, exc: ApiProblem) -> JSONResponse:
        return _response(exc.problem)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            Issue(
                path=format_path(_strip_location(tuple(err["loc"]))),
                message=err["msg"],
                code=err["type"],
                severity="error",
            )
            for err in exc.errors()
        ]
        return _response(
            Problem(
                status=422,
                code="invalid_request",
                title="The request is not valid",
                detail=f"{len(issues)} problem(s) found.",
                issues=issues,
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _response(Problem(status=exc.status_code, code="http_error", title=str(exc.detail)))
