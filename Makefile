.PHONY: test inspect-local doctor-local smoke-local check-local

test:
	python3 -m pytest -q

inspect-local:
	python3 -m agentflow inspect examples/local-real-agents-kimi-smoke.yaml --output summary

doctor-local:
	python3 -m agentflow doctor examples/local-real-agents-kimi-smoke.yaml --output summary

smoke-local:
	python3 -m agentflow smoke --show-preflight

check-local: doctor-local smoke-local
