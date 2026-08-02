from tiktok_affiliate_report.api import app

# Local foundation only: bind to localhost; OIDC/auth belongs in the Phase-2 architecture layer.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
