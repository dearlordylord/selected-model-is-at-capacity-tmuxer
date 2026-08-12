#!/usr/bin/env bash

# Composer variants are semantic strategies, not versions: Codex uses both in
# current releases depending on the selected reasoning effort.
COMPOSER_STRATEGY_NAMES=()
COMPOSER_STRATEGY_GLYPHS=()
COMPOSER_STRATEGY_EMPTY_MATCHERS=()
COMPOSER_STRATEGY_CONTEXT_MATCHERS=()

composer_register_strategy() {
  local index=${#COMPOSER_STRATEGY_NAMES[@]}
  [ "$#" -eq 4 ] && [ -n "$1" ] && [ -n "$2" ] && [ -n "$3" ] && [ -n "$4" ] || return 1
  COMPOSER_STRATEGY_NAMES[index]=$1
  COMPOSER_STRATEGY_GLYPHS[index]=$2
  COMPOSER_STRATEGY_EMPTY_MATCHERS[index]=$3
  COMPOSER_STRATEGY_CONTEXT_MATCHERS[index]=$4
}

composer_register_strategy codex_standard_max $'\xe2\x80\xba' \
  composer_codex_placeholder_is_empty composer_codex_context_matches
composer_register_strategy codex_ultra $'\xc2\xbb' \
  composer_codex_placeholder_is_empty composer_codex_context_matches

COMPOSER_ESC=$'\x1b'
COMPOSER_FAINT_SGR='2'

# Return whether a semicolon-separated SGR parameter list is understood. Being
# deliberately conservative here makes unknown terminal formatting fail closed.
composer_sgr_is_supported() {
  local params="$1" part value mode i
  local parts=()

  [ -z "$params" ] && return 0                    # ESC[m is reset
  case "$params" in
    ';'*|*';'|*';;'*) return 1 ;;
  esac

  IFS=';' read -r -a parts <<<"$params"
  i=0
  while [ "$i" -lt "${#parts[@]}" ]; do
    part=${parts[$i]}
    [[ "$part" =~ ^[0-9]+$ ]] || return 1
    [ "${#part}" -le 3 ] || return 1
    value=$((10#$part))

    case "$value" in
      0|1|2|3|4|7|9|22|23|24|27|29|39|49)
        i=$((i + 1))
        ;;
      38|48)
        [ $((i + 1)) -lt "${#parts[@]}" ] || return 1
        mode=${parts[$((i + 1))]}
        [[ "$mode" =~ ^[0-9]+$ ]] || return 1
        [ "${#mode}" -le 3 ] || return 1
        mode=$((10#$mode))
        if [ "$mode" -eq 5 ]; then
          [ $((i + 2)) -lt "${#parts[@]}" ] || return 1
          part=${parts[$((i + 2))]}
          [[ "$part" =~ ^[0-9]+$ ]] || return 1
          [ "${#part}" -le 3 ] || return 1
          value=$((10#$part))
          [ "$value" -le 255 ] || return 1
          i=$((i + 3))
        elif [ "$mode" -eq 2 ]; then
          [ $((i + 4)) -lt "${#parts[@]}" ] || return 1
          for part in "${parts[$((i + 2))]}" "${parts[$((i + 3))]}" "${parts[$((i + 4))]}"; do
            [[ "$part" =~ ^[0-9]+$ ]] || return 1
            [ "${#part}" -le 3 ] || return 1
            value=$((10#$part))
            [ "$value" -le 255 ] || return 1
          done
          i=$((i + 5))
        else
          return 1
        fi
        ;;
      *)
        if { [ "$value" -ge 30 ] && [ "$value" -le 37 ]; } ||
           { [ "$value" -ge 40 ] && [ "$value" -le 47 ]; } ||
           { [ "$value" -ge 90 ] && [ "$value" -le 97 ]; } ||
           { [ "$value" -ge 100 ] && [ "$value" -le 107 ]; }; then
          i=$((i + 1))
        else
          return 1
        fi
        ;;
    esac
  done
}

# Parse one leading SGR into shared result variables. Only CSI ... m is accepted.
composer_parse_leading_sgr() {
  local text="$1" body
  COMPOSER_SGR_PARAMS=
  COMPOSER_SGR_REMAINDER=

  case "$text" in
    "${COMPOSER_ESC}["*) ;;
    *) return 1 ;;
  esac
  body=${text#"${COMPOSER_ESC}["}
  case "$body" in
    *m*) ;;
    *) return 1 ;;
  esac

  COMPOSER_SGR_PARAMS=${body%%m*}
  composer_sgr_is_supported "$COMPOSER_SGR_PARAMS" || return 1
  COMPOSER_SGR_REMAINDER=${body#*m}
}

# Remove permitted leading spacing and SGR formatting from a terminal row.
composer_strip_leading_formatting() {
  local text="$1" trimmed
  while [ -n "$text" ]; do
    trimmed=${text#"${text%%[![:space:]]*}"}
    if [ "$trimmed" != "$text" ]; then
      text=$trimmed
      continue
    fi
    case "$text" in
      "${COMPOSER_ESC}["*)
        composer_parse_leading_sgr "$text" || return 1
        text=$COMPOSER_SGR_REMAINDER
        ;;
      *) break ;;
    esac
  done
  printf '%s' "$text"
}

# Strip supported SGRs anywhere in a row, rejecting every other escape sequence.
composer_strip_all_formatting() {
  local text="$1" first plain=''
  while [ -n "$text" ]; do
    case "$text" in
      "${COMPOSER_ESC}["*)
        composer_parse_leading_sgr "$text" || return 1
        text=$COMPOSER_SGR_REMAINDER
        ;;
      "$COMPOSER_ESC"*) return 1 ;;
      *)
        first=${text%"${text#?}"}
        plain=$plain$first
        text=${text#?}
        ;;
    esac
  done
  printf '%s' "$plain"
}

# Match a composer-prompt row into shared result variables. A glyph only counts
# when it is the first visible character, so glyphs in drafts cannot be prompts.
composer_prompt_match() {
  local line="$1" visible glyph index
  COMPOSER_MATCH_STRATEGY_INDEX=
  COMPOSER_MATCH_SUFFIX=
  visible=$(composer_strip_leading_formatting "$line") || {
    for glyph in "${COMPOSER_STRATEGY_GLYPHS[@]}"; do
      case "$line" in *"$glyph"*) return 2 ;; esac
    done
    return 1
  }

  index=0
  while [ "$index" -lt "${#COMPOSER_STRATEGY_NAMES[@]}" ]; do
    glyph=${COMPOSER_STRATEGY_GLYPHS[$index]:-}
    [ -n "$glyph" ] || return 2
    case "$visible" in
      "$glyph"*)
        COMPOSER_MATCH_STRATEGY_INDEX=$index
        COMPOSER_MATCH_SUFFIX=${visible#"$glyph"}
        return 0
        ;;
    esac
    index=$((index + 1))
  done
  return 1
}

# Narrow prompt-recognition seam: print only the raw suffix after the glyph.
composer_prompt_suffix() {
  composer_prompt_match "$1" || return
  printf '%s' "$COMPOSER_MATCH_SUFFIX"
}

# Apply an SGR parameter list to the current faint state.
composer_update_faint_state() {
  local params="$1" part
  local style_parts=()
  COMPOSER_FAINT_STATE=${COMPOSER_FAINT_STATE:-0}
  [ -n "$params" ] || { COMPOSER_FAINT_STATE=0; return; }
  IFS=';' read -r -a style_parts <<<"$params"
  for part in "${style_parts[@]}"; do
    case "$((10#$part))" in
      0|22) COMPOSER_FAINT_STATE=0 ;;
      2) COMPOSER_FAINT_STATE=1 ;;
    esac
  done
}

# Validate placeholder content, requiring faint to remain active for visible text.
composer_placeholder_text_is_valid() {
  local text="$1" first visible=0
  COMPOSER_FAINT_STATE=1
  while [ -n "$text" ]; do
    case "$text" in
      "${COMPOSER_ESC}["*)
        composer_parse_leading_sgr "$text" || return 1
        composer_update_faint_state "$COMPOSER_SGR_PARAMS"
        text=$COMPOSER_SGR_REMAINDER
        ;;
      "$COMPOSER_ESC"*) return 1 ;;
      *)
        first=${text%"${text#?}"}
        case "$first" in
          [[:space:]]) ;;
          *) [ "$COMPOSER_FAINT_STATE" -eq 1 ] || return 1; visible=1 ;;
        esac
        text=${text#?}
        ;;
    esac
  done
  [ "$visible" -eq 1 ]
}

# Return success only for spaces/supported SGRs followed by the exact faint SGR
# and a valid visible placeholder. RGB's "2" therefore cannot masquerade as it.
composer_placeholder_is_empty() {
  local text="$1" trimmed
  while [ -n "$text" ]; do
    trimmed=${text#"${text%%[![:space:]]*}"}
    if [ "$trimmed" != "$text" ]; then
      text=$trimmed
      continue
    fi
    case "$text" in
      "${COMPOSER_ESC}["*)
        composer_parse_leading_sgr "$text" || return 1
        if [ "$COMPOSER_SGR_PARAMS" = "$COMPOSER_FAINT_SGR" ]; then
          composer_placeholder_text_is_valid "$COMPOSER_SGR_REMAINDER"
          return
        fi
        text=$COMPOSER_SGR_REMAINDER
        ;;
      *) return 1 ;;
    esac
  done
  return 1
}

# Codex chooses one of these placeholders for an empty main composer. Keeping
# provider semantics here prevents a dim menu/history row from becoming input.
composer_codex_placeholder_is_empty() {
  local suffix="$1" text
  composer_placeholder_is_empty "$suffix" || return 1

  while [ -n "$suffix" ]; do
    case "$suffix" in
      "${COMPOSER_ESC}["*)
        composer_parse_leading_sgr "$suffix" || return 1
        suffix=$COMPOSER_SGR_REMAINDER
        ;;
      [[:space:]]*) suffix=${suffix#?} ;;
      *) break ;;
    esac
  done
  text=$(composer_strip_all_formatting "$suffix") || return 1
  case "$text" in
    'Explain this codebase'|\
    'Summarize recent commits'|\
    'Implement {feature}'|\
    'Find and fix a bug in @filename'|\
    'Write tests for @filename'|\
    'Improve documentation in @filename'|\
    'Run /review on my current changes'|\
    'Use /skills to list available skills') return 0 ;;
    *) return 1 ;;
  esac
}

# Codex's composer is followed by a blank row and its final status footer. This
# layout evidence distinguishes it from prompt-shaped transcript and menu rows.
composer_codex_context_matches() {
  local row_index="$1" after="$2" line plain row=0 footer_seen=0
  while IFS= read -r line || [ -n "$line" ]; do
    row=$((row + 1))
    line=${line%$'\r'}
    plain=$(composer_strip_all_formatting "$line") || return 1
    plain=${plain#"${plain%%[![:space:]]*}"}
    plain=${plain%"${plain##*[![:space:]]}"}
    case "$row" in
      1) [ -z "$plain" ] || return 1 ;;
      2)
        case "$plain" in
          *' default · /'*|*' low · /'*|*' medium · /'*|*' high · /'*|\
          *' xhigh · /'*|*' max · /'*|*' ultra · /'*) footer_seen=1 ;;
          *) return 1 ;;
        esac
        ;;
      *) [ -z "$plain" ] || return 1 ;;
    esac
  done <<<"$after"
  [ "$row_index" -ge 0 ] && [ "$footer_seen" -eq 1 ]
}

# Classify a captured terminal frame. Strategy-specific context proves that the
# last prompt-shaped row is an actual composer before its empty matcher runs.
composer_frame_is_empty() {
  local frame="$1" line status found=0 index=0 candidate_row=-1
  local strategy_index=-1 suffix='' empty_matcher context_matcher after=''
  local lines=()
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    lines[${#lines[@]}]=$line
    composer_prompt_match "$line"
    status=$?
    case "$status" in
      0)
        found=1
        candidate_row=$index
        strategy_index=$COMPOSER_MATCH_STRATEGY_INDEX
        suffix=$COMPOSER_MATCH_SUFFIX
        ;;
      2) return 1 ;;
    esac
    index=$((index + 1))
  done <<<"$frame"

  [ "$found" -eq 1 ] || return 1
  empty_matcher=${COMPOSER_STRATEGY_EMPTY_MATCHERS[$strategy_index]:-}
  context_matcher=${COMPOSER_STRATEGY_CONTEXT_MATCHERS[$strategy_index]:-}
  [ "$(type -t "$empty_matcher")" = function ] || return 1
  [ "$(type -t "$context_matcher")" = function ] || return 1

  index=$((candidate_row + 1))
  while [ "$index" -lt "${#lines[@]}" ]; do
    [ "$index" -eq $((candidate_row + 1)) ] || after=$after$'\n'
    after=$after${lines[$index]}
    index=$((index + 1))
  done
  "$context_matcher" "$candidate_row" "$after" || return 1
  "$empty_matcher" "$suffix"
}
