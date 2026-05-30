.PHONY: all demo smoke test

all: demo smoke test

demo:
	@echo "Running demo for coderev-agents..."
	@echo "See README for setup."

smoke:
	@echo "Running smoke tests for coderev-agents..."
	./smoke_test.sh

test:
	@echo "Running unit and integration tests for coderev-agents..."
	python3 -m pytest tests/
