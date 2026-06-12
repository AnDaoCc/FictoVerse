(() => {
  const prefs = window.__USER_PREFS__ || {};
  const I18N = window.__I18N__ || {};
  const t = (key, fallback = "") => I18N[key] || fallback || key;

  const playQueue = [];
  let playing = false;
  let currentAudio = null;
  let currentUtter = null;

  const backend = () => {
    const b = String(prefs.tts_backend || "edge").toLowerCase();
    return b === "openai" ? "openai_compatible" : b;
  };
  const enabled = () => !!prefs.tts_enabled;
  const autoPlay = () => !!prefs.tts_auto_play;

  const stripForTts = (text) => {
    let raw = String(text || "").trim();
    if (!raw) return "";
    raw = raw.replace(/```[\s\S]*?```/g, " ");
    raw = raw.replace(/`[^`]+`/g, " ");
    raw = raw.replace(/!\[[^\]]*\]\([^)]+\)/g, " ");
    raw = raw.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
    raw = raw.replace(/<[^>]+>/g, " ");
    raw = raw.replace(/[#*_~>|]/g, " ");
    raw = raw.replace(/\s+/g, " ").trim();
    return raw;
  };

  const extractMessageText = (wrap) => {
    if (!wrap) return "";
    const bubble = wrap.querySelector(".bubble");
    if (!bubble) return "";
    const clone = bubble.cloneNode(true);
    clone.querySelectorAll(".thinking-block, .msg-actions, .speak-btn, .msg-edit-form").forEach((el) => el.remove());
    return stripForTts(clone.querySelector(".content")?.textContent || "");
  };

  const charVoiceMap = () => {
    const map = {};
    const list = window.__WORLD_CHARACTERS__ || [];
    list.forEach((c) => {
      if (c && c.id) map[c.id] = c.tts_voice || "";
    });
    return map;
  };

  const resolveVoice = (wrap) => {
    if (!wrap) return prefs.tts_voice || "";
    const explicit = wrap.dataset.ttsVoice || "";
    if (explicit) return explicit;
    const charId = wrap.dataset.characterId || "";
    if (charId) {
      const fromMap = charVoiceMap()[charId];
      if (fromMap) return fromMap;
    }
    const b = backend();
    if (b === "openai_compatible") return prefs.tts_openai_voice || "alloy";
    if (b === "custom_http") return prefs.tts_voice || "default";
    return prefs.tts_voice || "";
  };

  const applySpeakerAttrs = (wrap, speaker) => {
    if (!wrap || !speaker) return;
    if (speaker.character_id) wrap.dataset.characterId = speaker.character_id;
    if (speaker.world_id) wrap.dataset.worldId = speaker.world_id;
    if (speaker.tts_voice) wrap.dataset.ttsVoice = speaker.tts_voice;
  };

  const markSpeaking = (wrap, on) => {
    const bubble = wrap?.querySelector(".bubble");
    if (bubble) bubble.classList.toggle("is-speaking", on);
  };

  const stopAll = () => {
    playQueue.length = 0;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    currentUtter = null;
    playing = false;
    document.querySelectorAll(".bubble.is-speaking").forEach((el) => el.classList.remove("is-speaking"));
  };

  const speakBrowser = (text, voiceName, wrap) =>
    new Promise((resolve) => {
      if (!window.speechSynthesis) {
        resolve();
        return;
      }
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = parseFloat(prefs.tts_rate || "1") || 1;
      utter.lang = document.documentElement.lang || "zh-CN";
      if (voiceName) {
        const voice = window.speechSynthesis.getVoices().find((v) => v.name === voiceName);
        if (voice) utter.voice = voice;
      }
      currentUtter = utter;
      utter.onend = () => {
        currentUtter = null;
        markSpeaking(wrap, false);
        resolve();
      };
      utter.onerror = () => {
        currentUtter = null;
        markSpeaking(wrap, false);
        resolve();
      };
      markSpeaking(wrap, true);
      window.speechSynthesis.speak(utter);
    });

  const speakApi = async (text, wrap) => {
    const body = {
      text,
      voice: resolveVoice(wrap),
      rate: parseFloat(prefs.tts_rate || "1") || 1,
      character_id: wrap?.dataset.characterId || "",
      world_id: wrap?.dataset.worldId || "",
    };
    const resp = await fetch("/api/tts/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error("TTS API failed");
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    return new Promise((resolve, reject) => {
      const audio = new Audio(url);
      currentAudio = audio;
      markSpeaking(wrap, true);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        markSpeaking(wrap, false);
        resolve();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        markSpeaking(wrap, false);
        reject(new Error("audio play failed"));
      };
      audio.play().catch(reject);
    });
  };

  const runQueue = async () => {
    if (playing) return;
    playing = true;
    while (playQueue.length) {
      const job = playQueue.shift();
      if (!job) continue;
      const { wrap, text, voice } = job;
      try {
        if (backend() === "browser") {
          await speakBrowser(text, voice, wrap);
        } else {
          await speakApi(text, wrap);
        }
      } catch (_err) {
        if (backend() !== "browser") {
          await speakBrowser(text, prefs.tts_voice || "", wrap);
        }
      }
    }
    playing = false;
  };

  const enqueueSpeak = (wrap, { manual = false } = {}) => {
    if (!enabled() && !manual) return;
    const text = extractMessageText(wrap);
    if (!text) return;
    const voice = backend() === "browser" ? resolveVoice(wrap) || prefs.tts_voice || "" : resolveVoice(wrap);
    playQueue.push({ wrap, text, voice });
    runQueue();
  };

  const speakMessage = (wrap) => {
    if (!wrap) return;
    enqueueSpeak(wrap, { manual: true });
  };

  const autoSpeakMessage = (wrap) => {
    if (!enabled() || !autoPlay()) return;
    enqueueSpeak(wrap, { manual: false });
  };

  window.__NWMedia = window.__NWMedia || {};
  Object.assign(window.__NWMedia, {
    speakMessage,
    autoSpeakMessage,
    stopAll,
    resolveVoice,
    applySpeakerAttrs,
    extractMessageText,
    enqueueSpeak,
  });
})();
