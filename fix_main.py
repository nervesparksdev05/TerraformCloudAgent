import re

with open('app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. module doc
content = re.sub(r'<<<<<<< HEAD\n"""app/main\.py — TerraBot FastAPI entry point \(GCP-only, interactive workflow\)\."""\n=======\n("""app/main\.py — TerraBot FastAPI entry point \(AWS-only, interactive workflow\)\.""")\n>>>>>>> origin-n/feature/backend-update', r'\1', content)

# 2. Imports FeedbackRequest
content = re.sub(r'<<<<<<< HEAD\n    FeedbackRequest,\n=======\n>>>>>>> origin-n/feature/backend-update', r'    FeedbackRequest,\n', content)

# 3. logger message
content = re.sub(r'<<<<<<< HEAD\nlogger\.info\("Starting %s v%s \(GCP-only mode\)", config\.APP_NAME, config\.APP_VERSION\)\n=======\n(logger\.info\("Starting %s v%s \(AWS Free Tier mode\)", config\.APP_NAME, config\.APP_VERSION\))\n>>>>>>> origin-n/feature/backend-update', r'\1', content)

# 4. lifespan Redis
content = re.sub(r'<<<<<<< HEAD\n    redis_url = os\.getenv\("REDIS_URL", "redis://redis:6379"\)\n    try:\n        redis_client = redis\.from_url\(redis_url, encoding="utf-8", decode_responses=True\)\n        await redis_client\.ping\(\)\n        logger\.info\("Connected to Redis at %s", redis_url\)\n    except Exception as e:\n        logger\.warning\("Redis unavailable: %s — rate limiting bypassed\.", e\)\n        redis_client = None\n    yield\n    if redis_client:\n        await redis_client\.close\(\)\n=======\n(.*?)>>>>>>> origin-n/feature/backend-update', r'\1', content, flags=re.DOTALL)

# 5. app description
content = re.sub(r'<<<<<<< HEAD\n    description=config\.APP_DESCRIPTION \+ " — GCP Interactive Workflow",\n=======\n(    description=config\.APP_DESCRIPTION \+ " — AWS Interactive Workflow",)\n>>>>>>> origin-n/feature/backend-update', r'\1', content)

# 6. _get_run_or_404
content = re.sub(r'<<<<<<< HEAD\n(def _get_run_or_404\(run_id: str\):.*?def _build_agent_request\(terraform_params: dict\) -> AgentRequest:\n    return AgentRequest\(\n        request=terraform_params,\n        provider=)"gcp",\n=======\ndef _build_agent_request\(terraform_params: dict\) -> AgentRequest:\n    return AgentRequest\(\n        request=terraform_params,\n        provider="aws",\n>>>>>>> origin-n/feature/backend-update', r'\1"aws",', content, flags=re.DOTALL)

# 7. root provider
content = re.sub(r'<<<<<<< HEAD\n        "provider": "GCP",\n=======\n        "provider": "AWS",\n>>>>>>> origin-n/feature/backend-update', '        "provider": "AWS",', content)

# 8. health provider
content = re.sub(r'<<<<<<< HEAD\n        "provider":      "gcp",\n        "auth_required": config\.REQUIRE_AUTH,\n=======\n(.*?)>>>>>>> origin-n/feature/backend-update', r'\1', content, flags=re.DOTALL)

# 9. doc comments
content = re.sub(r'<<<<<<< HEAD\n    """\n    Stream bot response via SSE\. Delegates all LLM logic to process_message,\n    then streams the returned text character by character\.\n    """\n=======\n>>>>>>> origin-n/feature/backend-update', r'    """\n    Stream bot response via SSE. Delegates all LLM logic to process_message,\n    then streams the returned text character by character.\n    """', content)
content = re.sub(r'<<<<<<< HEAD\n        # Stream the bot response text in chunks\n=======\n>>>>>>> origin-n/feature/backend-update', r'        # Stream the bot response text in chunks', content)
content = re.sub(r'<<<<<<< HEAD\n        # Auto-generate Terraform if conversation just completed\n=======\n>>>>>>> origin-n/feature/backend-update', r'        # Auto-generate Terraform if conversation just completed', content)

# 10. submit_feedback
content = re.sub(r'<<<<<<< HEAD\n(@app\.post\("/conversations/\{session_id\}/feedback".*?)\n=======\n>>>>>>> origin-n/feature/backend-update', r'\1\n', content, flags=re.DOTALL)

# 11. list_conversations
content = re.sub(r'<<<<<<< HEAD\n(async def list_conversations.*?# /sessions is removed — was a duplicate of /conversations)\n=======\nasync def list_conversations\(limit: int = 20, x_user_id: Optional\[str\] = Header\(None\)\):\n    await check_rate_limit\(x_user_id or "anonymous", redis_client\)\n    return conversation_manager\.list_sessions\(limit=limit\)\n\n\n@app\.get\("/sessions"\)\nasync def list_sessions\(limit: int = 20, user: Optional\[Dict\] = Depends\(get_current_user\)\):\n    try:\n        return conversation_manager\.list_sessions\(limit=limit\)\n    except Exception as e:\n        logger\.error\("list_sessions failed: %s", e, exc_info=True\)\n        raise HTTPException\(status_code=500, detail=str\(e\)\)\n>>>>>>> origin-n/feature/backend-update', r'\1', content, flags=re.DOTALL)

# 12. create_run provider
content = re.sub(r'<<<<<<< HEAD\n    request\.provider = "gcp"\n    try:\n        run = run_manager\.create_run\(request\)\n        logger\.info\("\[%s\] Created GCP run", run\.run_id\)\n=======\n(    request\.provider = "aws"\n    try:\n        run = run_manager\.create_run\(request\)\n        logger\.info\("\[%s\] Created AWS run", run\.run_id\))\n>>>>>>> origin-n/feature/backend-update', r'\1', content)

# 13. _get_run_or_404 calls
replace_404 = r'<<<<<<< HEAD\n    run = _get_run_or_404\(run_id\)\n=======\n    run = run_manager\.get_run\(run_id\)\n    if not run:\n        raise HTTPException\(status_code=404, detail=f"Run \{run_id\} not found"\)\n>>>>>>> origin-n/feature/backend-update'
content = re.sub(replace_404, r'    run = _get_run_or_404(run_id)', content)

# 14. chat plan AWS
content = re.sub(r'<<<<<<< HEAD\n            f"Explain the Terraform plan briefly using GCP terminology\\.\\n\\n"\n=======\n            f"Explain the Terraform plan briefly using AWS terminology\\.\\n\\n"\n>>>>>>> origin-n/feature/backend-update', r'            f"Explain the Terraform plan briefly using AWS terminology.\n\n"', content)

# 15. get_run_files
replace_404_2 = r'<<<<<<< HEAD\n    run = _get_run_or_404\(run_id\)\n=======\n    run = run_manager\.get_run\(run_id\)\n    if not run:\n        raise HTTPException\(status_code=404, detail=f"Run \{run_id\} not found"\)\n>>>>>>> origin-n/feature/backend-update'
content = re.sub(replace_404_2, r'    run = _get_run_or_404(run_id)', content)

# 16. workflow aws replan
content = re.sub(r'<<<<<<< HEAD\n    background_tasks\.add_task\(workflow_engine\.revalidate_and_replan, run_id, "gcp"\)\n=======\n(    # revalidate_and_replan now re-sanitizes before planning\n    background_tasks\.add_task\(workflow_engine\.revalidate_and_replan, run_id, "aws"\))\n>>>>>>> origin-n/feature/backend-update', r'\1', content)

# 17. redeploy endpoint
content = re.sub(r'<<<<<<< HEAD\n=======\n(@app\.post\("/runs/\{run_id\}/redeploy".*?)\n>>>>>>> origin-n/feature/backend-update', r'\1', content, flags=re.DOTALL)

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
