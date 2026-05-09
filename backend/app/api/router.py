from fastapi import APIRouter

from .auth import router as auth_router
from .developers import router as developers_router
from .digests import router as digests_router
from .orgs import router as orgs_router
from .slack_commands import router as slack_commands_router
from .webhooks.github import router as github_webhook_router
from .webhooks.jira import router as jira_webhook_router
from .webhooks.slack import router as slack_webhook_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(orgs_router)
router.include_router(developers_router)
router.include_router(digests_router)
router.include_router(slack_commands_router)
router.include_router(github_webhook_router)
router.include_router(slack_webhook_router)
router.include_router(jira_webhook_router)
