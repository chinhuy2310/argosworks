#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai_client.py — Universal AI Provider Client (OpenAI, Gemini, DeepSeek, Claude, Ollama, Groq, OpenRouter)
다중 API Key 순환(Round-Robin) 및 장애 시 보조 제공자 자동 전환(Multi-Provider Fallback) 지원
"""

import os
import json
import urllib.request
import urllib.error
import re
import threading
import time
from utils.logging import log_line
from utils.text import guess_category, VALID_CATEGORIES

# Concurrency control: Limit simultaneous AI API outbound calls to 32 (out of 128 workers)
# This guarantees that at least 96 workers in the 128-thread pool remain
# completely responsive for UI navigation, dashboard, CRUD, and static file serving.
_AI_CONCURRENCY_SEMAPHORE = threading.Semaphore(32)

# Default endpoints and protocols for popular providers
PROVIDER_CONFIGS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-3.5-flash-lite",
        "protocol": "openai"
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-3.5-flash-lite",
        "protocol": "openai"
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "protocol": "openai"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "protocol": "openai"
    },
    "claude": {
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-5",
        "protocol": "anthropic"
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-5",
        "protocol": "anthropic"
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "protocol": "openai"
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1",
        "protocol": "openai"
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "google/gemini-2.5-flash",
        "protocol": "openai"
    },
    "custom": {
        "base_url": "",
        "default_model": "",
        "protocol": "openai"
    }
}

def get_provider_api_keys(raw):
    """API Key 문자열 파싱 (복수 키 지원: 쉼표/세미콜론/줄바꿈 구분 다중 키 목록 반환)"""
    if not raw:
        return []
    if isinstance(raw, list):
        return [k.strip() for k in raw if isinstance(k, str) and k.strip()]
    if isinstance(raw, str):
        return [k.strip() for k in re.split(r"[,;\n\r]+", raw) if k.strip()]
    return []


def _normalize_provider_config(provider, model, api_key, base_url, enabled=True):
    p = (provider or "gemini").lower().strip()
    p_info = PROVIDER_CONFIGS.get(p, {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "protocol": "openai"
    })
    protocol = "anthropic" if p in ("claude", "anthropic") else p_info.get("protocol", "openai")
    return {
        "enabled": bool(enabled),
        "provider": p,
        "model": (model or p_info.get("default_model") or "").strip(),
        "base_url": (base_url or p_info.get("base_url") or "").rstrip("/"),
        "protocol": protocol,
        "api_key": api_key if isinstance(api_key, str) else ""
    }


def get_ai_config(cfg):
    """주(Primary) AI 설정 정규화"""
    ai = cfg.get("ai") or {}
    legacy_anthropic = cfg.get("anthropic", {})

    provider = (ai.get("provider") or ("claude" if legacy_anthropic.get("api_key") else "gemini")).lower().strip()
    enabled = ai.get("enabled")
    if enabled is None:
        enabled = legacy_anthropic.get("enabled", False)

    api_key = ai.get("api_key") or legacy_anthropic.get("api_key", "")
    model = ai.get("model") or legacy_anthropic.get("model") or ""
    base_url = ai.get("base_url") or ""

    return _normalize_provider_config(provider, model, api_key, base_url, enabled=enabled)


def get_ai_fallback_config(cfg):
    """보조(Fallback / Failover) AI 설정 정규화"""
    ai = cfg.get("ai") or {}
    fb = ai.get("fallback") or {}
    if not isinstance(fb, dict):
        fb = {}

    enabled = fb.get("enabled", False)
    provider = fb.get("provider", "openai")
    model = fb.get("model", "")
    base_url = fb.get("base_url", "")
    api_key = fb.get("api_key", "")

    if os.environ.get("AI_FALLBACK_ENABLED"):
        enabled = os.environ["AI_FALLBACK_ENABLED"].strip().lower() in ("1", "true", "yes", "on")
    if os.environ.get("AI_FALLBACK_PROVIDER"):
        provider = os.environ["AI_FALLBACK_PROVIDER"].strip().lower()
    if os.environ.get("AI_FALLBACK_MODEL"):
        model = os.environ["AI_FALLBACK_MODEL"].strip()
    if os.environ.get("AI_FALLBACK_BASE_URL"):
        base_url = os.environ["AI_FALLBACK_BASE_URL"].strip()
    if os.environ.get("AI_FALLBACK_API_KEY"):
        api_key = os.environ["AI_FALLBACK_API_KEY"].strip()

    return _normalize_provider_config(provider, model, api_key, base_url, enabled=enabled)


# ─────────────────────────────────────────────────────────────
# Low-level 단일 요청 실행 함수
# ─────────────────────────────────────────────────────────────

def _execute_ai_raw_single(prov, api_key, prompt, max_tokens, timeout):
    """단일 제공자 및 단일 API Key로 텍스트 완성 호출"""
    protocol = prov["protocol"]
    base_url = (prov.get("base_url") or "").rstrip("/")
    model = (prov.get("model") or "").strip()

    if prov.get("provider") == "custom":
        if not base_url:
            return None, "missing_base_url", "Custom AI Base URL이 입력되지 않았습니다."
        if not model:
            return None, "missing_model", "Custom AI 모델명(Model Name)이 입력되지 않았습니다."

    try:
        if protocol == "anthropic":
            url = f"{base_url}/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            body = json.dumps({
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }).encode("utf-8")
        else:
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key or 'ollama'}",
                "content-type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            }
            if prov.get("provider") == "openai" or str(model).startswith(("o1", "o3", "gpt-5")):
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens
            body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if protocol == "anthropic":
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            return (text if text else "OK"), None, ""
        else:
            choices = data.get("choices", [])
            if choices and "message" in choices[0]:
                content = choices[0]["message"].get("content")
                if content is not None:
                    return content, None, ""
                # Nếu model dùng reasoning token hết quota hoặc trả về finish_reason='length' với content=None
                finish_reason = choices[0].get("finish_reason")
                if finish_reason in ("stop", "length"):
                    return "OK", None, ""
            return None, "empty_response", "응답 본문이 비어있습니다."

    except urllib.error.HTTPError as e:
        err_msg = ""
        try:
            err_msg = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        return None, e.code, err_msg
    except Exception as e:
        return None, "error", str(e)


def _execute_ai_chat_completion_single(prov, api_key, messages, tools, tool_choice, max_tokens, timeout):
    """단일 제공자 및 단일 API Key로 채팅 완성 및 Tool Calling 호출"""
    protocol = prov["protocol"]
    base_url = (prov.get("base_url") or "").rstrip("/")
    model = (prov.get("model") or "").strip()

    if prov.get("provider") == "custom":
        if not base_url:
            return None, "missing_base_url", "Custom AI Base URL이 입력되지 않았습니다."
        if not model:
            return None, "missing_model", "Custom AI 모델명(Model Name)이 입력되지 않았습니다."

    try:
        if protocol == "anthropic":
            url = f"{base_url}/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            system_content = ""
            api_messages = []
            for m in messages:
                role = m.get("role")
                if role == "system":
                    system_content += m.get("content", "") + "\n"
                elif role == "assistant":
                    blocks = []
                    if m.get("content"):
                        blocks.append({"type": "text", "text": m.get("content")})
                    if m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            args = tc.get("function", {}).get("arguments", "{}")
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except Exception:
                                    args = {}
                            blocks.append({
                                "type": "tool_use",
                                "id": tc.get("id"),
                                "name": tc.get("function", {}).get("name"),
                                "input": args
                            })
                    api_messages.append({"role": "assistant", "content": blocks if blocks else ""})
                elif role == "tool":
                    tool_res = {
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id"),
                        "content": str(m.get("content", ""))
                    }
                    if api_messages and api_messages[-1]["role"] == "user" and isinstance(api_messages[-1]["content"], list):
                        api_messages[-1]["content"].append(tool_res)
                    else:
                        api_messages.append({
                            "role": "user",
                            "content": [tool_res]
                        })
                else:
                    api_messages.append({"role": role, "content": m.get("content", "")})

            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": api_messages
            }
            if system_content.strip():
                payload["system"] = system_content.strip()

            if tools:
                anthropic_tools = []
                for t in tools:
                    func = t.get("function", {})
                    anthropic_tools.append({
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {})
                    })
                payload["tools"] = anthropic_tools

            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content_blocks = data.get("content", [])
            text_parts = []
            tool_calls = []
            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)
                        }
                    })

            msg = {"role": "assistant", "content": "\n".join(text_parts) if text_parts else None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            return {"choices": [{"message": msg}]}, None, ""

        else:
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key or 'ollama'}",
                "content-type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
            }
            is_openai_reasoning = (
                prov.get("provider") == "openai" or
                str(model).lower().startswith(("o1", "o3", "gpt-5")) or
                "o1-" in str(model).lower() or
                "o3-" in str(model).lower()
            )
            if max_tokens is not None:
                if is_openai_reasoning:
                    payload["max_completion_tokens"] = max_tokens
                else:
                    payload["max_tokens"] = max_tokens

            if tools:
                payload["tools"] = tools
                if tool_choice:
                    payload["tool_choice"] = tool_choice

            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data, None, ""

    except urllib.error.HTTPError as e:
        err_msg = ""
        try:
            err_msg = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass

        # Auto-fallback: handle max_tokens vs max_completion_tokens mismatch
        if e.code == 400 and ("max_tokens" in err_msg or "max_completion_tokens" in err_msg):
            try:
                retried_payload = dict(payload)
                if "max_tokens" in retried_payload:
                    val = retried_payload.pop("max_tokens")
                    retried_payload["max_completion_tokens"] = val
                elif "max_completion_tokens" in retried_payload:
                    val = retried_payload.pop("max_completion_tokens")
                    retried_payload["max_tokens"] = val

                body = json.dumps(retried_payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(url, data=body, method="POST", headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8")), None, ""
            except Exception:
                pass

        return None, e.code, err_msg
    except Exception as e:
        return None, "error", str(e)


# ─────────────────────────────────────────────────────────────
# 상위 레벨 오케스트레이터: Key 우선 순환 후 Provider Fallback 실행
# ─────────────────────────────────────────────────────────────

def call_ai_raw(cfg, prompt, max_tokens=600, timeout=30):
    """
    프롬프트를 전송하여 텍스트 응답을 반환
    주(Primary) 제공자 호출 후 실패 시 보조(Fallback) 제공자로 전환
    """
    primary = get_ai_config(cfg)
    if not primary["enabled"]:
        return None

    # Guard: Use non-blocking acquire with quick timeout so excessive AI requests fail fast
    # rather than holding worker threads hostage indefinitely.
    acquired = _AI_CONCURRENCY_SEMAPHORE.acquire(timeout=5.0)
    if not acquired:
        log_line("[AI Client] ⚠️ AI Concurrency limit reached (16 slots busy). Skipping AI enhancement.")
        return None

    try:
        fallback = get_ai_fallback_config(cfg)
        providers_to_try = [primary]
        if fallback["enabled"] and (fallback["api_key"] or fallback["provider"] == "ollama"):
            providers_to_try.append(fallback)

        for prov_idx, prov in enumerate(providers_to_try):
            is_primary = (prov_idx == 0)
            p_name = prov["provider"]
            keys = get_provider_api_keys(prov.get("api_key"))
            if not keys:
                if p_name == "ollama":
                    keys = [""]
                else:
                    continue

            for key_idx, api_key in enumerate(keys):
                res, err_type, err_msg = _execute_ai_raw_single(prov, api_key, prompt, max_tokens, timeout)
                if res is not None:
                    if not is_primary:
                        log_line(f"[AI Client] 보조 AI ({p_name} - {prov['model']}) raw 응답 성공")
                    try:
                        from services.ai_usage_service import record_ai_usage
                        p_est = len(prompt) // 3
                        c_est = len(res) // 3
                        record_ai_usage("system", "", p_name, prov.get("model", ""), p_est, c_est, p_est + c_est, "", "raw")
                    except Exception:
                        pass
                    return res

                log_line(f"[AI Client] {p_name.upper()} 키 #{key_idx+1} 오류 ({err_type}): {str(err_msg)[:120]}")
                if len(keys) > 1 and key_idx < len(keys) - 1:
                    log_line(f"[AI Client] 🔄 다음 API 키 (#{key_idx+2})로 자동 교체 시도...")

            if is_primary and len(providers_to_try) > 1:
                fb = providers_to_try[1]
                log_line(f"[AI Client] ⚠️ 주 AI ({primary['provider']}) 가용 불가 → 보조 AI ({fb['provider']} - {fb['model']})로 자동 전환...")

        return None
    finally:
        _AI_CONCURRENCY_SEMAPHORE.release()


def call_ai_chat_completions(cfg, messages, tools=None, tool_choice="auto",
                              max_tokens=2048, timeout=90):
    """
    OpenAI 호환 /chat/completions 엔드포인트를 호출한다. (멀티턴 ReAct 에이전트 및 Tool Calling)
    주(Primary) 제공자 호출 후 실패 시 보조(Fallback) 제공자로 전환 (다중 키 자동 회전 지원)
    """
    primary = get_ai_config(cfg)
    if not primary["enabled"]:
        return None

    acquired = _AI_CONCURRENCY_SEMAPHORE.acquire(timeout=5.0)
    if not acquired:
        log_line("[AI Client] ⚠️ AI Concurrency limit reached (16 slots busy). Chat completion unavailable temporarily.")
        return None

    try:
        fallback = get_ai_fallback_config(cfg)
        providers_to_try = [primary]
        if fallback["enabled"] and (fallback["api_key"] or fallback["provider"] == "ollama"):
            providers_to_try.append(fallback)

        for prov_idx, prov in enumerate(providers_to_try):
            is_primary = (prov_idx == 0)
            p_name = prov["provider"]
            keys = get_provider_api_keys(prov.get("api_key"))
            if not keys:
                if p_name == "ollama":
                    keys = [""]
                else:
                    continue

            for key_idx, api_key in enumerate(keys):
                res, err_type, err_msg = _execute_ai_chat_completion_single(
                    prov, api_key, messages, tools, tool_choice, max_tokens, timeout
                )
                if res is not None:
                    if not is_primary:
                        log_line(f"[AI Client] 보조 AI ({p_name} - {prov['model']}) 채팅/도구 응답 성공")
                    try:
                        from services.ai_usage_service import record_ai_usage
                        usage = res.get("usage") if isinstance(res, dict) else {}
                        p_tok = (usage or {}).get("prompt_tokens", 0)
                        c_tok = (usage or {}).get("completion_tokens", 0)
                        t_tok = (usage or {}).get("total_tokens", p_tok + c_tok)
                        record_ai_usage("chat_agent", "", p_name, prov.get("model", ""), p_tok, c_tok, t_tok, "", "chat_agent")
                    except Exception:
                        pass
                    return res

                log_line(f"[AI Client] {p_name.upper()} 키 #{key_idx+1} 오류 ({err_type}): {str(err_msg)[:120]}")
                if len(keys) > 1 and key_idx < len(keys) - 1:
                    log_line(f"[AI Client] 🔄 다음 API 키 (#{key_idx+2})로 자동 교체 시도...")

            if is_primary and len(providers_to_try) > 1:
                fb = providers_to_try[1]
                log_line(f"[AI Client] ⚠️ 주 AI ({primary['provider']}) 가용 불가 → 보조 AI ({fb['provider']} - {fb['model']})로 자동 전환...")

        return None
    finally:
        _AI_CONCURRENCY_SEMAPHORE.release()


def call_ai_classify(cfg, memo, filenames, dept_name):
    """Classify work record category and generate 1-2 sentence Korean summary"""
    prompt = (
        "다음은 사내 인수인계/업무 기록입니다. 아래 후보 카테고리 중 하나를 고르고, "
        "한국어로 1~2문장 요약을 만들어주세요. 반드시 마크다운 코드블록 없이 순수 JSON만 출력하세요:\n"
        '{"category": "...", "summary": "..."}\n\n'
        "후보 카테고리: " + ", ".join(VALID_CATEGORIES) + "\n"
        "작성 부서: " + (dept_name or "") + "\n"
        "메모: " + (memo or "(없음)") + "\n"
        "첨부파일: " + (", ".join(filenames) if filenames else "(없음)")
    )

    text = call_ai_raw(cfg, prompt, max_tokens=300, timeout=20)
    if not text:
        return None

    try:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        if parsed.get("category") not in VALID_CATEGORIES:
            parsed["category"] = guess_category(memo)
        return parsed
    except Exception as e:
        log_line("AI 분류 응답 JSON 파싱 실패:", e)
        return None


def call_ai_answer(cfg, question, candidates):
    """Answer employee questions based on internal search context"""
    if candidates:
        parts = []
        for i, r in enumerate(candidates, 1):
            rid = str(r.get("id", ""))
            if r.get("jira"):
                src = "Jira " + r["jira"]["key"]
            elif rid.startswith("product-") or rid.startswith("pim-"):
                src = "제품 [%s] %s" % (r.get("category", "제품"), r.get("title", ""))
            elif rid.startswith("schedule-") or str(r.get("doc_id", "")).startswith("schedule:"):
                src = "캘린더 일정"
            else:
                src = "인수인계 기록 #%s" % rid

            # Combine summary and memo so full specs/features are preserved
            text_blocks = []
            if r.get("summary"):
                text_blocks.append(str(r["summary"]))
            if r.get("memo") and r["memo"] != r.get("summary"):
                text_blocks.append(str(r["memo"]))
            body_text = "\n".join(text_blocks)[:1800]

            assignee = r.get("assignee") or r.get("ownerName") or ""
            extra_info = ""
            if r.get("parentSummary"):
                extra_info = " (상위업무: %s)" % r.get("parentSummary")
            parts.append(
                "[%d] (%s) 제목: %s%s / 담당자: %s / 부서: %s / 카테고리: %s / 날짜: %s\n내용:\n%s"
                % (i, src, r.get("title", ""), extra_info, assignee, r.get("org", ""), r.get("category", ""),
                   r.get("date", ""), body_text)
            )
        context = "\n\n".join(parts)
    else:
        context = "(관련 자료를 찾지 못했습니다.)"

    prompt = (
        "당신은 사내 인수인계 및 업무 관리를 돕는 AI 어시스턴트입니다. "
        "아래는 사내 업무 기록, Jira 티켓, 일정 및 제품 정보에서 검색된 관련 자료입니다.\n"
        "제공된 자료를 바탕으로 사용자의 질문에 정확하고 구체적으로 답하세요.\n"
        "규칙:\n"
        "1. 사용자의 질문 언어(한국어, 베트남어, 영어 등)를 자동으로 감지하여 반드시 **동일한 언어**로 자연스럽게 답변하세요. (예: 질문이 베트남어면 답변도 100% 베트남어로 작성, 영어 질문은 영어로, 한국어 질문은 한국어로 작성)\n"
        "2. **인사말(안녕하세요 등)이나 자기소개는 일체 생략**하고, 본론(핵심 답변 내용)부터 바로 작성하세요.\n"
        "3. MAS(다수공급자계약), OTA(무선 펌웨어 업데이트), GIS 등 공공조달 및 기술 용어 질의 시, 용어의 공식적 정의(예: 조달청 나라장터 다수공급자계약 등)와 함께 사내에서 진행 중인 관련 업무(Jira 티켓, 제품군 등)를 유기적으로 연결하여 정확하게 안내하세요.\n"
        "4. 제품(카메라, 전광판, 녹화기 등)에 대한 질의일 경우:\n"
        "   - 제품명, 모델명, 분류(예: 열화상&실화상 카메라)를 명시하고, 제품의 주요 용도 및 특징(센서, 해상도, 줌배율 등)을 본문에 상세히 설명하세요.\n"
        "   - 규격 사양 및 조달 정보를 안내하세요.\n"
        "5. **답변 본문에 외부 웹 링크(URL), 카탈로그 링크, 첨부파일명 목록을 일체 삽입하지 마세요.** 사용자는 화면 하단의 관련 자료 카드(출처 목록)를 직접 클릭하여 상세 사양, 첨부 카탈로그 PDF 및 원본 페이지를 확인할 수 있으므로, 답변 본문은 제품 및 업무의 핵심 내용 설명에만 집중하세요.\n"
        "6. 답변 중간에 근거가 되는 자료 번호를 표시하세요 (예: [1], [2]).\n"
        "7. 자료에 없는 내용은 임의로 지어내지 마세요.\n\n"
        "관련 자료:\n" + context + "\n\n질문: " + question
    )

    # 사용자 검색 시 최대 대기 시간을 7초로 제한하여 초과 시 즉시 검색 결과로 폴백
    text = call_ai_raw(cfg, prompt, max_tokens=1200, timeout=7)
    return text.strip() if text else None


# Backward-compatibility aliases
call_claude_classify = call_ai_classify
call_claude_answer = call_ai_answer
