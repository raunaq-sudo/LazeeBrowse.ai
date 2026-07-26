# from app import app
# import uvicorn
# if __name__ == "__main__":
    
#     # uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
#     uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
import sys
import traceback

print("STARTING...", flush=True)

try:
    import uvicorn
    print("Uvicorn imported", flush=True)

    from app import app
    print("App imported", flush=True)

    uvicorn.run(app, host="127.0.0.1", port=8000)

except Exception:
    print("ERROR OCCURRED:", flush=True)
    traceback.print_exc()