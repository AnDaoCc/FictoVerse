"""SillyTavern / OpenAI 兼容 Preset JSON 解析。"""

from __future__ import annotations



import json

from typing import Any



from novel_world.core.exceptions import ValidationError

from novel_world.modules.ai.domain.generation_config import GenerationConfig

from novel_world.modules.ai.domain.prompt_layers import PromptLayers

from novel_world.modules.ai.domain.prompt_slots import PromptProfile, PromptSlot



_LAYER_IDENTIFIERS = {

    "main",

    "jailbreak",

    "nsfw",

    "post_history",

    "postfix",

    "authors_note",

    "an",

    "system_extra",

    "persona",

    "scenario",

    "impersonate",

    "continue",

    "quiet",

    "char_description",

    "world_info",

}





def _prompt_identifier(item: dict[str, Any]) -> str:

    for key in ("identifier", "name", "id"):

        raw = str(item.get(key) or "").strip().lower()

        if raw:

            return raw

    return ""





def _extract_prompt_profile(raw: dict[str, Any]) -> PromptProfile:

    slots: list[PromptSlot] = []

    prompts = raw.get("prompts")

    if isinstance(prompts, list):

        for item in prompts:

            if not isinstance(item, dict):

                continue

            ident = _prompt_identifier(item)

            content = str(item.get("content") or item.get("system_prompt") or "").strip()

            if not ident:

                continue

            depth = item.get("depth")

            slots.append(

                PromptSlot(

                    identifier=ident,

                    content=content,

                    enabled=bool(item.get("enabled", True)),

                    depth=int(depth) if depth is not None else None,

                )

            )



    order_raw = raw.get("prompt_order") or raw.get("promptOrder") or []

    order: list[str] = []

    if isinstance(order_raw, list):

        for item in order_raw:

            if isinstance(item, dict):

                ident = _prompt_identifier(item)

                if ident:

                    order.append(ident)

            elif isinstance(item, str) and item.strip():

                order.append(item.strip().lower())



    if not order and slots:

        order = [s.identifier for s in slots]



    gen_data: dict[str, Any] = {}

    temp = raw.get("temperature", raw.get("temp"))

    if temp is not None:

        gen_data["temperature"] = temp

    top_p = raw.get("top_p", raw.get("topP"))

    if top_p is not None:

        gen_data["top_p"] = top_p

    max_tokens = raw.get("openai_max_tokens", raw.get("max_tokens", raw.get("max_length")))

    if max_tokens is not None:

        gen_data["max_tokens"] = max_tokens

    rep_pen = raw.get("repetition_penalty", raw.get("rep_pen"))

    if rep_pen is not None:

        gen_data["repetition_penalty"] = rep_pen

    stop = raw.get("stop", raw.get("stop_sequences"))

    if stop is not None:

        gen_data["stop"] = stop



    return PromptProfile(

        slots=slots,

        order=order,

        generation=GenerationConfig.from_dict(gen_data),

        template="chat",

    )





def _profile_to_layers(profile: PromptProfile) -> dict[str, Any]:

    return profile.to_layers().to_dict()





def parse_st_preset(data: bytes | dict[str, Any]) -> dict[str, Any]:

    if isinstance(data, (bytes, bytearray)):

        try:

            raw = json.loads(data.decode("utf-8"))

        except (UnicodeDecodeError, json.JSONDecodeError) as exc:

            raise ValidationError(f"Preset JSON 无效：{exc}") from exc

    else:

        raw = data

    if not isinstance(raw, dict):

        raise ValidationError("Preset JSON 必须是对象。")



    profile = _extract_prompt_profile(raw)

    layers = PromptLayers.from_dict(_profile_to_layers(profile))

    return {

        "generation": profile.generation.to_dict(),

        "prompt_layers": layers.to_dict(),

        "prompt_profile": profile.to_dict(),

        "name": str(raw.get("name") or raw.get("preset_name") or "").strip(),

    }





def apply_preset_to_prefs(existing: dict[str, Any], preset: dict[str, Any]) -> dict[str, Any]:

    merged = dict(existing)

    if preset.get("generation"):

        merged["default_generation"] = preset["generation"]

    if preset.get("prompt_layers"):

        merged["default_prompt_layers"] = preset["prompt_layers"]

    if preset.get("prompt_profile"):

        merged["default_prompt_profile"] = preset["prompt_profile"]

    return merged


