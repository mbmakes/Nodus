# -*- coding: utf-8 -*-
import os
import re
import time
import base64
import inspect
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(override=True)

from agent_core import NodusAgent
from memory_manager import NodusMemory
from tools import NodusTools

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(
    page_title="Nodus Platform",
    page_icon="⚙️",
    layout="wide"
)

memory = NodusMemory()
agent = NodusAgent(api_key=OPENROUTER_API_KEY, gemini_api_key=GEMINI_API_KEY)
tools = NodusTools()

# EKRAN HER ACILISTA TEMIZ BASLASIN
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_action" not in st.session_state:
    st.session_state.pending_action = None

def clean_display_text(text: str) -> str:
    """Modelin arkada urettigi XML, JSON veya teknik etiketleri kullanici icin temizler."""
    if not text:
        return ""
    text = re.sub(r'<tool_call>[\s\S]*?</tool_call>', '', text)
    text = re.sub(r'<arg_key>[\s\S]*?</arg_key>', '', text)
    text = re.sub(r'<arg_value>[\s\S]*?</arg_value>', '', text)
    text = text.split("EYLEM_DETAYI:")[0]
    text = re.sub(r'\{[\s\r\n]*"action"[\s\r\n]*:[\s\S]*?\}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

@st.cache_data(ttl=600)
def get_available_free_models():
    reliable_defaults = [
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free"
    ]
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        if res.status_code == 200:
            data = res.json().get("data", [])
            free_models = [
                m["id"] for m in data
                if m.get("id", "").endswith(":free")
                and "guard" not in m.get("id", "").lower()
                and "moderation" not in m.get("id", "").lower()
                and "gemini-2.0-flash-exp" not in m.get("id", "").lower()
                and "qwen-2.5-coder-32b" not in m.get("id", "").lower()
                and "mistral-small-24b" not in m.get("id", "").lower()
                and "nex" not in m.get("id", "").lower()
                and "nemotron" not in m.get("id", "").lower()
            ]
            if free_models:
                return free_models
    except Exception:
        pass
    return reliable_defaults

def get_workspace_directory():
    if hasattr(tools, "path_guard") and hasattr(tools.path_guard, "allowed_dir"):
        return tools.path_guard.allowed_dir
    elif hasattr(tools, "guard") and hasattr(tools.guard, "allowed_dir"):
        return tools.guard.allowed_dir
    elif hasattr(tools, "workspace_dir"):
        return tools.workspace_dir
    elif hasattr(tools, "allowed_workspace"):
        return tools.allowed_workspace
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "allowed_workspace")

def is_safe_action(action_info: dict) -> tuple:
    action = action_info.get("action", "")
    params = action_info.get("params", {})

    if action in ["read_file", "list_files", "solve_math", "search_codebase"]:
        return True, ""

    if action in ["write_file", "apply_patch"]:
        fname = params.get("filename", "").lower()
        critical_files = ["app.py", "agent_core.py", "tools.py", "memory_manager.py", ".env", "requirements.txt"]
        if any(fname.endswith(cf) for cf in critical_files):
            return False, f"Kritik sistem dosyasi degistirilmeye calisiliyor: {fname}"
        return True, ""

    if action == "execute_code":
        code = params.get("code", "")
        high_risk_triggers = [
            r"os\.remove", r"os\.unlink", r"os\.rmdir", r"shutil\.rmtree",
            r"subprocess", r"os\.system", r"os\.popen",
            r"urllib\.request", r"curl ", r"wget ",
            r"steam", r"shutdown", r"taskkill"
        ]
        for trigger in high_risk_triggers:
            if re.search(trigger, code, re.IGNORECASE):
                return False, f"Riskli sistem / ag / silme komutu tespit edildi: `{trigger}`"
        return True, ""

    return False, f"Tanimlanmamis / Harici Eylem: {action}"

def execute_with_healing(action_info: dict, active_model: str, fetched_models: list) -> tuple:
    exec_start_time = time.time()
    result = agent.execute_approved_action(action_info)
    action_type = action_info.get("action", "")
    params = action_info.get("params", {})

    healing_attempts = 0
    repair_logs = []

    while action_type == "execute_code" and not result.get("success") and healing_attempts < 2:
        healing_attempts += 1
        stderr_msg = result.get("stderr", "").strip()
        failed_code = params.get("code", "")

        heal_prompt = (
            "Calistirilan Python kodu su hatayi verdi:\n[HATA]: "
            + stderr_msg
            + "\n[HATALI KOD]: "
            + failed_code
            + "\nGorev: Hatayi analiz et. Hatayi gidererek calisacak Python kodunu EYLEM_DETAYI blogu icinde 'execute_code' olarak yeniden olustur."
        )

        heal_resp = agent.call_model(active_model, heal_prompt, [], fetched_models)
        heal_action = agent.parse_action(heal_resp)

        if heal_action and heal_action.get("action") == "execute_code":
            repair_logs.append(f"⚠️ **Onarim #{healing_attempts}:** Hata duzeltildi.")
            action_info = heal_action
            params = heal_action.get("params", {})
            result = agent.execute_approved_action(heal_action)
        else:
            break

    workspace_dir = get_workspace_directory()
    generated_images = []
    if os.path.exists(workspace_dir):
        for fname in os.listdir(workspace_dir):
            if fname.lower().endswith((".png", ".jpg", ".jpeg")):
                full_img_path = os.path.join(workspace_dir, fname)
                if os.path.getmtime(full_img_path) >= (exec_start_time - 1.5):
                    generated_images.append(full_img_path)

    log_prefix = "\n".join(repair_logs) + "\n\n" if repair_logs else ""
    
    if action_type == "write_file":
        out_text = f"✅ **`{params.get('filename')}`** dosyası kaydedildi."
    elif action_type == "apply_patch":
        out_text = f"✅ **`{params.get('filename')}`** dosyası güncellendi."
    elif action_type == "read_file":
        fname = params.get('filename')
        if result.get("success"):
            out_text = f"📄 **`{fname}` dosyası içeriği:**\n```python\n{result.get('content', '')}\n```"
        else:
            out_text = f"❌ `{fname}` dosyası okunamadı."
    elif action_type == "list_files":
        files = result.get("files", [])
        if files:
            file_list = "\n".join([f"- `{f}`" for f in files])
            out_text = f"📂 **Çalışma Alanındaki Dosyalar:**\n{file_list}"
        else:
            out_text = "📂 Çalışma alanında henüz dosya yok."
    elif action_type == "search_codebase":
        matches = result.get("matches", {})
        if isinstance(matches, dict) and matches:
            formatted = "\n".join([f"**{f}**:\n" + "\n".join([f"  - {line}" for line in lines]) for f, lines in matches.items()])
            out_text = f"🔍 **Arama Sonuçları:**\n{formatted}"
        else:
            out_text = "🔍 Aranan ifade dosyalarda bulunamadı."
    elif action_type == "solve_math":
        out_text = f"✅ **Analitik Çözüm:** `{result.get('result', '')}`"
    elif action_type == "execute_code":
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        if result.get("success"):
            out_text = f"{log_prefix}⚙️ **Çalıştırma Başarılı:**\n```\n{stdout if stdout else 'Kod hatasız yürütüldü.'}\n```"
        else:
            out_text = f"{log_prefix}❌ **Hata:**\n```\n{stderr}\n```"
    else:
        out_text = "✅ İşlem tamamlandı."

    return out_text, generated_images

# --- SOL KONTROL PANELI ---
with st.sidebar:
    st.title("⚙️ Nodus Kontrol")
    
    if not OPENROUTER_API_KEY:
        st.error("OpenRouter Anahtari Bulunamadi (.env)")
    if not GEMINI_API_KEY:
        st.warning("GEMINI_API_KEY eklenmedi (.env)")

    dev_mode = st.toggle("🛠️ Gelistirici Modu", value=False)

    st.markdown("---")
    st.subheader("Model Secimi")
    fetched_models = get_available_free_models()
    model_options = ["🤖 Otomatik (Dinamik Puanlama)"] + fetched_models
    selected_model_option = st.selectbox("Aktif Model:", model_options)

    st.markdown("---")
    st.subheader("📂 Calisma Alani (Workspace)")
    current_files = tools.list_files()
    if current_files:
        selected_file = st.selectbox("Dosya Onizle:", current_files)
        if selected_file:
            file_data = tools.read_file(selected_file)
            if file_data.get("success"):
                st.text_area("Icerik:", file_data.get("content", ""), height=150, disabled=True)
                st.download_button(label=f"⬇️ Indir", data=file_data.get("content", ""), file_name=selected_file)
    else:
        st.caption("Henuz dosya olusturulmadi.")

    st.markdown("---")
    st.subheader("📌 Kalici Kurallar (Pinned Facts)")
    facts = memory.get_facts()
    for idx, fact in enumerate(facts):
        col1, col2 = st.columns([5, 1])
        col1.write(f"- {fact}")
        if col2.button("❌", key=f"del_fact_{idx}"):
            memory.remove_fact(idx)
            st.rerun()

    new_fact = st.text_input("Yeni kural ekle:", placeholder="Orn: SI birim sistemi kullan.")
    if st.button("Kurali Kaydet"):
        if new_fact:
            memory.add_fact(new_fact)
            st.rerun()

    st.markdown("---")
    col_rst1, col_rst2 = st.columns(2)
    if col_rst1.button("Sohbeti Sil"):
        memory.reset_history_only()
        st.session_state.messages = []
        st.session_state.pending_action = None
        st.rerun()
    if col_rst2.button("Tumunu Sifirla"):
        memory.reset_everything()
        st.session_state.messages = []
        st.session_state.pending_action = None
        st.rerun()

# --- ANA SOHBET ALANI ---
st.title("Nodus Engine")
st.caption("Otonom Muhendislik ve Karar Destek Platformu")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        clean_content = clean_display_text(msg.get("content", ""))
        if clean_content:
            st.markdown(clean_content)
        if msg.get("user_image"):
            st.image(f"data:image/png;base64,{msg['user_image']}", width=400)
        if "images" in msg and msg["images"]:
            for img_path in msg["images"]:
                if os.path.exists(img_path):
                    st.image(img_path, caption=os.path.basename(img_path), use_container_width=True)

if st.session_state.pending_action:
    action_info = st.session_state.pending_action
    risk_reason = action_info.get("_risk_reason", "Kritik islem tespiti.")
    
    st.error(f"🛑 **Guvenlik Uyarisi (Riskli Islem):**\n{risk_reason}")
    st.caption("Bu islem guvenli calisma havuzunun disina ciktigi icin manuel onayiniz gereklidir.")

    if dev_mode:
        st.json(action_info)

    col_app, col_rej = st.columns([1, 4])
    if col_app.button("⚠️ Riski Biliyorum, Onayla", type="primary"):
        with st.spinner("Kritik islem yurutuluyor..."):
            active_m = selected_model_option if not selected_model_option.startswith("🤖") else "meta-llama/llama-3.3-70b-instruct:free"
            res_text, imgs = execute_with_healing(action_info, active_m, fetched_models)
            st.session_state.pending_action = None
            msg_payload = {"role": "assistant", "content": res_text, "images": imgs}
            st.session_state.messages.append(msg_payload)
            memory.save_chat_turn("[Kritik Eylem Onaylandi]", res_text)
            st.rerun()

    if col_rej.button("❌ Islemi Reddet"):
        st.session_state.pending_action = None
        cancel_text = "Kritik islem kullanici tarafindan reddedildi."
        st.session_state.messages.append({"role": "assistant", "content": cancel_text})
        memory.save_chat_turn("[Kritik Eylem Reddedildi]", cancel_text)
        st.rerun()

chat_input_params = inspect.signature(st.chat_input).parameters

if "accept_file" in chat_input_params:
    chat_prompt = st.chat_input(
        "Talimatinizi veya teknik sorunuzu girin...",
        accept_file=True,
        file_type=["png", "jpg", "jpeg"]
    )
else:
    with st.popover("➕ Ekran Goruntusu / Gorsel Ekle"):
        st.file_uploader("Gorsel secin:", type=["png", "jpg", "jpeg"], key="legacy_file_upload")
    chat_prompt = st.chat_input("Talimatinizi veya teknik sorunuzu girin...")

if chat_prompt:
    uploaded_files = []
    user_prompt = ""

    if hasattr(chat_prompt, "text"):
        user_prompt = (chat_prompt.text or "").strip()
        uploaded_files = chat_prompt.files or []
    elif isinstance(chat_prompt, dict):
        user_prompt = (chat_prompt.get("text") or "").strip()
        uploaded_files = chat_prompt.get("files") or []
    else:
        user_prompt = str(chat_prompt).strip()
        if st.session_state.get("legacy_file_upload"):
            uploaded_files = [st.session_state["legacy_file_upload"]]

    if not user_prompt and uploaded_files:
        user_prompt = "Gonderilen gorseli analiz et, tum olculeri cikar ve adim adim Python ile coz."

    if user_prompt or uploaded_files:
        has_image = bool(uploaded_files)
        base64_img = None
        final_prompt_for_agent = user_prompt

        perception_success = True
        perception_error_msg = ""

        if has_image:
            img_file = uploaded_files[0]
            img_bytes = img_file.read()
            base64_img = base64.b64encode(img_bytes).decode("utf-8")
            mime = getattr(img_file, "type", "image/png") or "image/png"

            with st.spinner("Gemini teknik cizimi sayisallastiriyor..."):
                ok, res_text = agent.transcribe_engineering_image(img_bytes, mime)
                if ok:
                    final_prompt_for_agent = (
                        f"{user_prompt}\n\n"
                        f"--- [YUKLENEN GORSELIN VE DIYAGRAMIN TEKNIK DOKUMU (PERCEPTION)] ---\n"
                        f"{res_text}\n"
                        f"------------------------------------------------------------------"
                    )
                else:
                    perception_success = False
                    perception_error_msg = res_text

        with st.chat_message("user"):
            st.markdown(user_prompt)
            if base64_img:
                st.image(f"data:image/png;base64,{base64_img}", width=400)

        st.session_state.messages.append({
            "role": "user",
            "content": user_prompt,
            "user_image": base64_img
        })

        if not perception_success:
            err_box = f"⚠️ **Görsel Algılama Başarısız:**\n{perception_error_msg}"
            with st.chat_message("assistant"):
                st.markdown(err_box)
            st.session_state.messages.append({"role": "assistant", "content": err_box})
            st.rerun()

        if selected_model_option.startswith("🤖"):
            routing_res = agent.select_best_model(final_prompt_for_agent, fetched_models)
            active_model = routing_res[0] if isinstance(routing_res, tuple) else routing_res
        else:
            active_model = selected_model_option

        with st.chat_message("assistant"):
            model_tag = active_model.split('/')[1] if '/' in active_model else active_model
            with st.spinner(f"Nodus düşünüyor ({model_tag})..."):
                # Ekranda gorunmese dahi kalici hafizayi modele aktar
                past_context = memory.get_recent_messages()
                api_history = [{"role": m["role"], "content": m["content"]} for m in past_context[-10:]]
                api_history.append({"role": "user", "content": final_prompt_for_agent})

                response = agent.call_model(active_model, final_prompt_for_agent, api_history, fetched_models)
                action = agent.parse_action(response)

                user_explanation = clean_display_text(response)

                if action:
                    is_safe, reason = is_safe_action(action)
                    if is_safe:
                        if user_explanation:
                            st.markdown(user_explanation)
                        with st.spinner("İşlem yürütülüyor..."):
                            res_text, imgs = execute_with_healing(action, active_model, fetched_models)
                            combined_reply = f"{user_explanation}\n\n{res_text}" if user_explanation else res_text
                            st.markdown(res_text)
                            if imgs:
                                for img in imgs:
                                    st.image(img, caption=os.path.basename(img), use_container_width=True)
                            st.session_state.messages.append({"role": "assistant", "content": combined_reply, "images": imgs})
                            memory.save_chat_turn(user_prompt, combined_reply)
                            st.rerun()
                    else:
                        if user_explanation:
                            st.markdown(user_explanation)
                        action["_risk_reason"] = reason
                        st.session_state.pending_action = action
                        st.rerun()
                else:
                    if user_explanation:
                        st.markdown(user_explanation)
                    else:
                        st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": user_explanation or response})
                    memory.save_chat_turn(user_prompt, user_explanation or response)