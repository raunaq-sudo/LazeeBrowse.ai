# from app import app
# import uvicorn
# if __name__ == "__main__":
    
#     # uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
#     uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
import traceback

print("STARTING...")

try:
    import uvicorn
    print("Uvicorn imported")

    from app import app
    print("App imported")

    uvicorn.run(app, host="127.0.0.1", port=8000)

except Exception:
    print("ERROR OCCURRED:")
    traceback.print_exc()

input("Press Enter to exit...")