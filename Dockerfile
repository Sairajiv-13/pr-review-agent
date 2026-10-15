FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home reviewer
USER reviewer

ENTRYPOINT ["pr-review"]
CMD ["--help"]
