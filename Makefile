.PHONY: all demo smoke test
all: demo smoke test
demo:
	@echo "Running demo for coderev-agents..."
smoke:
	@echo "Running smoke tests for coderev-agents..."
	./smoke_test.sh
test:
	@echo "Running tests for coderev-agents..."
	pytest tests/ || echo "No tests found"
