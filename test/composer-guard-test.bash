#!/usr/bin/env bash
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=../lib/composer-guard.bash
. "$ROOT/lib/composer-guard.bash"

failures=0
tests=0

assert_success() {
  local name="$1"
  shift
  tests=$((tests + 1))
  if "$@"; then
    printf 'ok %s\n' "$name"
  else
    printf 'not ok %s - expected success\n' "$name"
    failures=$((failures + 1))
  fi
}

assert_failure() {
  local name="$1"
  shift
  tests=$((tests + 1))
  if "$@"; then
    printf 'not ok %s - expected failure\n' "$name"
    failures=$((failures + 1))
  else
    printf 'ok %s\n' "$name"
  fi
}

assert_output() {
  local name="$1" expected="$2"
  shift 2
  tests=$((tests + 1))
  actual=$("$@")
  if [ "$actual" = "$expected" ]; then
    printf 'ok %s\n' "$name"
  else
    printf 'not ok %s - expected %q, got %q\n' "$name" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

while IFS='|' read -r name expected escaped_frame; do
  case "$name" in
    ''|'#'*) continue ;;
  esac

  tests=$((tests + 1))
  frame=$(printf '%b' "$escaped_frame")
  if composer_frame_is_empty "$frame"; then
    actual=empty
  else
    actual=nonempty
  fi

  if [ "$actual" != "$expected" ]; then
    printf 'not ok %s - expected %s, got %s\n' "$name" "$expected" "$actual"
    failures=$((failures + 1))
  else
    printf 'ok %s\n' "$name"
  fi
done < "$ROOT/test/fixtures/composer-frames.tsv"

# The three classifier responsibilities also expose narrow seams of their own.
assert_success 'sgr parser accepts RGB background' composer_sgr_is_supported '48;2;12;34;56'
assert_failure 'sgr parser rejects incomplete RGB background' composer_sgr_is_supported '48;2;12;34'
assert_failure 'sgr parser rejects overflowing extended-color mode' \
  composer_sgr_is_supported '48;18446744073709551618;1;2;3'
assert_output 'prompt matcher anchors the first visible glyph' $'\033[22m draft »' \
  composer_prompt_suffix $' \033[1m›\033[22m draft »'
assert_failure 'prompt matcher ignores embedded transcript glyphs' \
  composer_prompt_suffix 'output mentions ›'
assert_success 'placeholder matcher requires exact faint style' \
  composer_placeholder_is_empty $'\033[0m\033[48;5;12m \033[2mAsk Codex'
assert_failure 'placeholder matcher does not confuse RGB with faint' \
  composer_placeholder_is_empty $'\033[48;2;2;34;56m Ask Codex'

# Extending the semantic registry composes a glyph with context and empty matchers.
test_plain_placeholder_is_empty() {
  [ "$1" = ' Ready' ]
}
test_future_context_matches() {
  [ "$2" = 'future footer' ]
}
# shellcheck disable=SC2034 # arithmetic array subscript used by the unsets below
strategy_index=${#COMPOSER_STRATEGY_NAMES[@]}
composer_register_strategy future '^' test_plain_placeholder_is_empty test_future_context_matches
assert_success 'registry composes a future empty matcher without parser branches' \
  composer_frame_is_empty $'^ Ready\nfuture footer'
unset 'COMPOSER_STRATEGY_NAMES[strategy_index]'
unset 'COMPOSER_STRATEGY_GLYPHS[strategy_index]'
unset 'COMPOSER_STRATEGY_EMPTY_MATCHERS[strategy_index]'
unset 'COMPOSER_STRATEGY_CONTEXT_MATCHERS[strategy_index]'

printf '%s tests, %s failures\n' "$tests" "$failures"
[ "$failures" -eq 0 ]
