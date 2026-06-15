# Prompt Changelog

## v2 — Personal Context Injection
- **Date**: 2026-06-05
- **File**: `conversation_exploring_v2.md`
- **Change**: Added personal context injection section
  - 注入用户身份背景、情绪趋势、归因模式
  - 让AI能自然引用用户的历史话题
  - 不改变四步结构，只增强对话的延续感
- **Why**: 用户反馈"感觉每次对话都是新的"，需要让对话有延续性

## v1 — Initial Version
- **Date**: 2026-06-04
- **File**: `conversation_exploring_v1.md`
- **Change**: Initial prompt design with 4-step structure
  - empathy → attribution → challenge → closure
  - Structured JSON output in every response
  - 两种模式分离：exploring（引导） vs listening（倾听）
- **Why**: MVP需要验证"结构化引导能否帮用户归因"
