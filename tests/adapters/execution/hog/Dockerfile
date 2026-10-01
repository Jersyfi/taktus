# A unit that serves health and, on GET /v1/hog, allocates far more than its memory limit: the
# container adapter's memory-kill test (tests/adapters/execution/test_container.py). Built
# through tests/images.py, and only when this directory changed.
FROM python:3.13-slim
COPY hog.py /hog.py
CMD ["python3", "/hog.py"]
