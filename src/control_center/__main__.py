import uvicorn
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("src.control_center.app:app", host="127.0.0.1", port=8000, reload=False)
