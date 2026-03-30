#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/shouc/agentflow.git"
INSTALL_DIR="${AGENTFLOW_DIR:-$HOME/.agentflow}"
SKILL_DIR_CODEX="$HOME/.codex/skills/agentflow"
SKILL_DIR_CLAUDE="$HOME/.claude/skills/agentflow"

echo "AgentFlow Installer"
echo "==================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found. Install Python 3.11+ first."
  exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo "Error: Python 3.11+ required (found $PY_VERSION)"
  exit 1
fi
echo "✓ Python $PY_VERSION"

# Clone or update
if [ -d "$INSTALL_DIR" ]; then
  echo "Updating $INSTALL_DIR..."
  cd "$INSTALL_DIR" && git pull --quiet
else
  echo "Installing to $INSTALL_DIR..."
  git clone --quiet "$REPO" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
echo "✓ Repository ready"

# Create venv and install
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -e ".[dev]"
echo "✓ Python package installed"

# Add to PATH
BINDIR="$INSTALL_DIR/.venv/bin"
if ! echo "$PATH" | grep -q "$BINDIR"; then
  SHELL_RC=""
  if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
  elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
  elif [ -f "$HOME/.profile" ]; then
    SHELL_RC="$HOME/.profile"
  fi

  if [ -n "$SHELL_RC" ]; then
    if ! grep -q "agentflow" "$SHELL_RC" 2>/dev/null; then
      echo "" >> "$SHELL_RC"
      echo "# AgentFlow" >> "$SHELL_RC"
      echo "export PATH=\"$BINDIR:\$PATH\"" >> "$SHELL_RC"
      echo "✓ Added to PATH in $SHELL_RC"
    fi
  fi
fi

# Install skill for Codex
if command -v codex &>/dev/null; then
  mkdir -p "$SKILL_DIR_CODEX"
  cp "$INSTALL_DIR/skills/agentflow/SKILL.md" "$SKILL_DIR_CODEX/SKILL.md"
  echo "✓ Codex skill installed at $SKILL_DIR_CODEX"
else
  echo "· Codex not found (skip skill install)"
fi

# Install skill for Claude Code
if command -v claude &>/dev/null; then
  mkdir -p "$SKILL_DIR_CLAUDE"
  cp "$INSTALL_DIR/skills/agentflow/SKILL.md" "$SKILL_DIR_CLAUDE/SKILL.md"
  echo "✓ Claude Code skill installed at $SKILL_DIR_CLAUDE"
else
  echo "· Claude Code not found (skip skill install)"
fi

echo ""
echo "Done! Run: source ~/.bashrc && agentflow --help"
echo ""
echo "Quick start:"
echo "  agentflow init > pipeline.py"
echo "  agentflow run pipeline.py"
