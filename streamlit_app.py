"""
WhatsApp Auto Sender — Avro India Web Tool
"""
import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import requests, base64, io, os, time, hashlib
from pathlib import Path

st.set_page_config(
    page_title="WA Sender | Avro India",
    page_icon="📱",
    layout="wide"
)

# ════════════════════════════════════════════════
# PASSWORD GATE
# ════════════════════════════════════════════════
def _check_login():
    if st.session_state.get("_auth", False):
        return True
    st.markdown("""
    <style>
    .lb{max-width:420px;margin:6rem auto;padding:2.5rem 2rem;
        background:#f8f9fa;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.10);}
    .lt{text-align:center;margin-bottom:.5rem;}
    .ls{text-align:center;color:#888;margin-top:0;}
    </style>
    <div class="lb">
      <h1 class="lt">📱 Avro India</h1>
      <p class="ls">WhatsApp Auto Sender</p>
      <p class="ls">🔒 Authorized Users Only</p>
    </div>""", unsafe_allow_html=True)
    _, col, _ = st.columns([1,2,1])
    with col:
        pwd = st.text_input("Password", type="password", placeholder="Apna password daalo...")
        if st.button("Login →", type="primary", use_container_width=True):
            correct = st.secrets.get("app_password", "avro@2024")
            if pwd == correct:
                st.session_state["_auth"] = True
                st.rerun()
            else:
                st.error("❌ Galat password!")
        st.caption("💡 Password nahi pata? Ankit se poochho.")
    return False

if not _check_login():
    st.stop()

# ════════════════════════════════════════════════
AISENSY_URL = "https://backend.aisensy.com/campaign/t1/api/v2"
IMGBB_URL   = "https://api.imgbb.com/1/upload"

try:
    _KEY   = st.secrets.get("aisensy_key", "")
    _IMGBB = st.secrets.get("imgbb_key", "")
except Exception:
    _KEY   = ""
    _IMGBB = ""

CAMPAIGNS = ["Avro India Limited Dealer", "Avrodealers"]

try:
    from streamlit_drawable_canvas import st_canvas
    _CANVAS = True
except Exception:
    _CANVAS = False

# ── Fonts ──────────────────────────────────────
FONT_DIR = Path("/tmp/wa_fonts")
FONT_DIR.mkdir(exist_ok=True)

GOOGLE_FONTS = {
    "Roboto":          "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Regular.ttf",
    "Roboto Bold":     "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Bold.ttf",
    "Poppins":         "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf",
    "Poppins Bold":    "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf",
    "Montserrat":      "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Regular.ttf",
    "Montserrat Bold": "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf",
    "Open Sans":       "https://github.com/google/fonts/raw/main/apache/opensans/static/OpenSans-Regular.ttf",
    "Lato":            "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf",
    "Lato Bold":       "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf",
}

@st.cache_resource(show_spinner="Fonts load ho rahe hain...")
def load_fonts():
    paths = {}
    for name, url in GOOGLE_FONTS.items():
        dest = FONT_DIR / f"{name.replace(' ','_')}.ttf"
        if not dest.exists():
            try:
                r = requests.get(url, timeout=15); r.raise_for_status()
                dest.write_bytes(r.content)
            except Exception:
                continue
        if dest.exists():
            paths[name] = str(dest)
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.exists(fp):
            paths.setdefault("System Default", fp); break
    return paths

FONT_PATHS = load_fonts()
FONT_LIST  = list(FONT_PATHS.keys()) or ["Default"]

def get_pil_font(name, size):
    path = FONT_PATHS.get(name)
    if path:
        try: return ImageFont.truetype(path, int(size))
        except Exception: pass
    return ImageFont.load_default()

# ── Session state ──────────────────────────────
for k, v in {"boxes":[], "template_pil":None, "df":None,
              "img_hash":None, "editing_idx":0}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Image helpers ──────────────────────────────
def draw_preview(pil, boxes, ei=None):
    img  = pil.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    lf   = get_pil_font("Roboto", max(14, min(pil.size)//40))
    for i, box in enumerate(boxes):
        x,y,w,h = int(box["x"]),int(box["y"]),int(box["w"]),int(box["h"])
        col = "#1565C0" if i==ei else "#E53935"
        draw.rectangle([x,y,x+w,y+h], outline=col, width=3 if i==ei else 2)
        txt = f" {i+1}. {box['label']} "
        bb = draw.textbbox((x,y), txt, font=lf)
        draw.rectangle([bb[0],max(0,bb[1]-2),bb[2],bb[3]+2], fill=col)
        draw.text((x+2,max(0,y-lf.size)), txt, fill="white", font=lf)
    return img

def render_image(pil, boxes, row):
    img  = pil.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    for box in boxes:
        x,y,w,h = int(box["x"]),int(box["y"]),int(box["w"]),int(box["h"])
        text  = str(row.get(box["label"], f"[{box['label']}]"))
        fsize = int(box.get("size",40))
        font  = get_pil_font(box.get("font","Roboto"), fsize)
        color = box.get("color","#000000")
        align = box.get("align","center")
        words = text.split(); lines, cur = [], ""
        for word in words:
            t = (cur+" "+word).strip()
            if draw.textbbox((0,0),t,font=font)[2] <= w-8: cur=t
            else:
                if cur: lines.append(cur)
                cur=word
        if cur: lines.append(cur)
        if not lines: lines=[""]
        lh = fsize+4; ty = y+max(0,(h-len(lines)*lh)//2)
        for line in lines:
            bb = draw.textbbox((0,0),line,font=font); tw=bb[2]-bb[0]
            tx = x+(w-tw)//2 if align=="center" else (x+w-tw-4 if align=="right" else x+4)
            draw.text((tx,ty), line, font=font, fill=color); ty+=lh
    return img

def upload_imgbb(img_pil, api_key):
    buf=io.BytesIO(); img_pil.save(buf,format="JPEG",quality=92)
    b64=base64.b64encode(buf.getvalue()).decode()
    r=requests.post(IMGBB_URL,data={"key":api_key,"image":b64},timeout=30)
    r.raise_for_status(); return r.json()["data"]["url"]

def normalize(phone, cc="91"):
    try: phone=int(float(str(phone)))
    except: pass
    p=str(phone).strip().replace(" ","").replace("-","").replace("+","").replace(".","").lstrip("0")
    if p.startswith(cc) and len(p)==len(cc)+10: return p
    return (cc+p) if len(p)==10 else p

def send_aisensy(api_key, campaign, phone, uname, params, img_url=""):
    payload={"apiKey":api_key,"campaignName":campaign,"destination":phone,
             "userName":uname,"templateParams":params,"source":"new-landing-page form",
             "buttons":[],"carouselCards":[],"location":{},"attributes":{},"paramsFallbackValue":{}}
    if img_url: payload["media"]={"url":img_url,"filename":"sample_media"}
    r=requests.post(AISENSY_URL,json=payload,timeout=30)
    if not r.ok: raise Exception(f"{r.status_code}: {r.text}")
    try: return r.json()
    except: return {"status":"sent"}

# ════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════
st.markdown("<h1 style='margin-bottom:2px'>📱 WhatsApp Auto Sender</h1>"
            "<p style='color:#888;margin-top:0'>Avro India — Excel → Image → WhatsApp</p>",
            unsafe_allow_html=True)

# ════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state["_auth"] = False; st.rerun()
    st.divider()
    st.markdown("### 📋 Campaign")
    camp_mode = st.radio("", ["List se choose karo","Khud likhna hai"],
                         horizontal=True, label_visibility="collapsed")
    campaign = st.selectbox("Campaign", CAMPAIGNS) if camp_mode=="List se choose karo" \
               else st.text_input("Campaign Name", value=CAMPAIGNS[0])
    st.divider()
    with st.expander("🔑 API Keys", expanded=False):
        ai_key    = st.text_input("AI Sensy Key", value=_KEY,   type="password")
        imgbb_key = st.text_input("imgbb Key",    value=_IMGBB, type="password")
        username  = st.text_input("Sender Name",  value="Avro india")
    st.divider()
    with st.expander("📡 Other Settings", expanded=False):
        send_img  = st.checkbox("Image attach karo", value=True)
        cc        = st.text_input("Country Code", value="91")
        delay_sec = st.slider("Delay (sec)", 2, 30, 5)
    st.divider()
    st.success(f"Campaign: **{campaign}**")
    st.caption("🏢 Avro India Internal Tool")

# ════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["  1️⃣  Image Template  ","  2️⃣  Excel Upload  ","  3️⃣  Preview & Send  "])

# ══════════════════════════
# TAB 1
# ══════════════════════════
with tab1:
    img_file = st.file_uploader("Template image upload karo", type=["png","jpg","jpeg","webp"])

    if img_file is not None:
        raw   = img_file.read()
        h_new = hashlib.md5(raw).hexdigest()
        # Sirf nayi image pe boxes reset karo
        if st.session_state.img_hash != h_new:
            st.session_state.template_pil = Image.open(io.BytesIO(raw)).convert("RGBA")
            st.session_state.boxes        = []
            st.session_state.img_hash     = h_new
            st.session_state.editing_idx  = 0

    if st.session_state.template_pil is None:
        st.info("👆 Apni template image upload karo")
        st.stop()

    pil = st.session_state.template_pil
    iw, ih = pil.size

    left_col, right_col = st.columns([3, 2])

    if _CANVAS:
        MAX_W = 820
        c_s = min(1.0, MAX_W/iw)
        cw, ch = int(iw*c_s), int(ih*c_s)
        canvas_bg = pil.convert("RGB").resize((cw,ch), Image.LANCZOS)
        sx, sy = iw/cw, ih/ch

        with left_col:
            st.subheader("🖱️ Mouse se Box Banao")
            mode_lbl = st.radio("Mode:", ["✏️ Draw (box khicho)","🔧 Edit / Delete"],
                                horizontal=True, key="cmode")
            canvas_mode = "rect" if "Draw" in mode_lbl else "transform"
            st.caption("Image pe **drag karo** → red box ban jayega" if canvas_mode=="rect"
                       else "Box click karo → **Delete key** dabao")
            res = st_canvas(background_image=canvas_bg, drawing_mode=canvas_mode,
                            key="canvas_main", stroke_color="#E53935", stroke_width=2,
                            fill_color="rgba(229,57,53,0.15)", height=ch, width=cw,
                            update_streamlit=True, display_toolbar=False)
            if res.json_data is not None:
                shapes = [o for o in res.json_data.get("objects",[]) if o.get("type")=="rect"]
                while len(st.session_state.boxes) < len(shapes):
                    idx = len(st.session_state.boxes)
                    st.session_state.boxes.append({"label":f"Field{idx+1}","font":"Roboto Bold",
                        "size":40,"color":"#000000","align":"center","x":0,"y":0,"w":100,"h":50})
                st.session_state.boxes = st.session_state.boxes[:len(shapes)]
                for i,s in enumerate(shapes):
                    st.session_state.boxes[i].update({
                        "x":s["left"]*sx,"y":s["top"]*sy,
                        "w":s["width"]*s.get("scaleX",1)*sx,
                        "h":s["height"]*s.get("scaleY",1)*sy})

        with right_col:
            st.subheader("✏️ Text Boxes")
            if not st.session_state.boxes:
                st.info("👈 Image pe rectangle **drag** karo")
            else:
                for i, box in enumerate(st.session_state.boxes):
                    with st.expander(f"📦 Box {i+1}: {box.get('label','')}",
                                     expanded=(i==len(st.session_state.boxes)-1)):
                        st.session_state.boxes[i]["label"] = st.text_input(
                            "Excel Column Name", value=box.get("label",""), key=f"lbl_{i}")
                        c1,c2 = st.columns(2)
                        fn = box.get("font","Roboto Bold")
                        with c1:
                            st.session_state.boxes[i]["font"] = st.selectbox("Font", FONT_LIST,
                                index=FONT_LIST.index(fn) if fn in FONT_LIST else 0, key=f"sfnt_{i}")
                            st.session_state.boxes[i]["size"] = st.number_input(
                                "Size",8,300,int(box.get("size",40)),key=f"ssz_{i}")
                        with c2:
                            st.session_state.boxes[i]["color"] = st.color_picker(
                                "Color",box.get("color","#000000"),key=f"scol_{i}")
                            st.session_state.boxes[i]["align"] = st.radio("Align",
                                ["left","center","right"],
                                index=["left","center","right"].index(box.get("align","center")),
                                horizontal=True,key=f"saln_{i}")
                        st.caption(f"X={int(box.get('x',0))} Y={int(box.get('y',0))} "
                                   f"W={int(box.get('w',0))} H={int(box.get('h',0))}px")
    else:
        # ── Slider fallback ──
        with left_col:
            st.subheader("🖼 Image Preview")
            ei = st.session_state.get("editing_idx", 0)
            if not st.session_state.boxes: ei = None
            elif ei >= len(st.session_state.boxes): ei = 0
            st.image(draw_preview(pil, st.session_state.boxes, ei), use_container_width=True)

        with right_col:
            st.subheader("✏️ Text Boxes")
            if st.button("➕ Naya Box Add Karo", type="primary", use_container_width=True):
                st.session_state.boxes.append({
                    "label": f"Field{len(st.session_state.boxes)+1}",
                    "x":iw//4,"y":ih//4,"w":iw//2,"h":ih//8,
                    "font":"Roboto Bold","size":40,"color":"#000000","align":"center"})
                st.session_state.editing_idx = len(st.session_state.boxes)-1
                st.rerun()

            if not st.session_state.boxes:
                st.info("Button dabao → box add hoga → sliders se adjust karo")
            else:
                ei = st.session_state.get("editing_idx", 0)
                if ei >= len(st.session_state.boxes): ei = 0
                opts = [f"Box {i+1}" for i in range(len(st.session_state.boxes))]
                sel  = st.radio("Box select karo:", opts, index=ei, horizontal=True, key="box_r")
                ei   = int(sel.split()[1])-1
                st.session_state.editing_idx = ei
                box  = st.session_state.boxes[ei]
                st.divider()
                st.session_state.boxes[ei]["label"] = st.text_input(
                    "Excel Column Name", value=box["label"], key=f"lbl_{ei}")
                st.markdown("**Position:**")
                st.session_state.boxes[ei]["x"] = st.slider("⬅➡ X",0,iw-1,int(box["x"]),key=f"sx_{ei}")
                st.session_state.boxes[ei]["y"] = st.slider("⬆⬇ Y",0,ih-1,int(box["y"]),key=f"sy_{ei}")
                st.session_state.boxes[ei]["w"] = st.slider("↔ W",10,iw,int(box["w"]),key=f"sw_{ei}")
                st.session_state.boxes[ei]["h"] = st.slider("↕ H",10,ih,int(box["h"]),key=f"sh_{ei}")
                st.markdown("**Text Style:**")
                c1,c2 = st.columns(2)
                with c1:
                    st.session_state.boxes[ei]["font"] = st.selectbox("Font",FONT_LIST,
                        index=FONT_LIST.index(box["font"]) if box["font"] in FONT_LIST else 0,key=f"sfnt_{ei}")
                    st.session_state.boxes[ei]["size"] = st.number_input("Size",8,300,int(box["size"]),key=f"ssz_{ei}")
                with c2:
                    st.session_state.boxes[ei]["color"] = st.color_picker("Color",box["color"],key=f"scol_{ei}")
                    st.session_state.boxes[ei]["align"] = st.radio("Align",["left","center","right"],
                        index=["left","center","right"].index(box.get("align","center")),
                        horizontal=True,key=f"saln_{ei}")
                if st.button("🗑 Delete Box", use_container_width=True):
                    st.session_state.boxes.pop(ei)
                    st.session_state.editing_idx = max(0,ei-1)
                    st.rerun()

# ══════════════════════════
# TAB 2
# ══════════════════════════
with tab2:
    st.subheader("Excel / CSV Upload")
    exc = st.file_uploader("File choose karo", type=["xlsx","xls","csv"], key="exc_up")
    if exc:
        try:
            df = pd.read_csv(exc) if exc.name.endswith(".csv") else pd.read_excel(exc)
            st.session_state.df = df
            st.success(f"✅ {len(df)} contacts  |  Columns: {', '.join(df.columns)}")
            st.dataframe(df, use_container_width=True, height=300)
        except Exception as e:
            st.error(f"Error: {e}")
    elif st.session_state.df is not None:
        st.success(f"✅ {len(st.session_state.df)} contacts loaded")
        st.dataframe(st.session_state.df, use_container_width=True, height=300)
    else:
        st.markdown("**Format:** Columns mein **Naam**, **Phone** rakhna • Excel (.xlsx) ya CSV")

# ══════════════════════════
# TAB 3
# ══════════════════════════
with tab3:
    df  = st.session_state.df
    pil = st.session_state.template_pil
    if df is None:  st.warning("⚠️ Tab 2 mein Excel upload karo"); st.stop()
    if pil is None: st.warning("⚠️ Tab 1 mein image upload karo"); st.stop()
    if not st.session_state.boxes: st.warning("⚠️ Tab 1 mein boxes add karo"); st.stop()

    cols = df.columns.tolist()
    c1,c2 = st.columns(2)
    with c1: phone_col = st.selectbox("📞 Phone column", cols)
    with c2: param_str = st.text_input("Template Params (blank=none)", value="")

    message = st.text_area("💬 WhatsApp Message",
        value="Namaste {Naam} ji!\n\nAapka invitation attached hai.\n\nAvro India", height=80)
    st.caption("Tip: {ColumnName} likhna jahan value aani chahiye")
    st.info(f"📋 Active Campaign: **{campaign}**", icon="✅")
    st.divider()

    st.subheader("👁 Preview")
    opts = df.apply(lambda r:" | ".join(str(r[c]) for c in cols[:3]),axis=1).tolist()
    prev_row = df.iloc[opts.index(st.selectbox("Contact:", opts))].to_dict()
    if st.button("🖼 Preview Generate Karo"):
        with st.spinner("..."): st.image(render_image(pil,st.session_state.boxes,prev_row),width=480)
    st.divider()

    st.subheader("📋 Contacts")
    ca,cb,_ = st.columns([1,1,4])
    with ca:
        if st.button("☑ Sab"):
            for idx in df.index: st.session_state[f"s_{idx}"] = True
    with cb:
        if st.button("☐ Clear"):
            for idx in df.index: st.session_state[f"s_{idx}"] = False

    selected = []
    for idx,row in df.iterrows():
        k = f"s_{idx}"
        if k not in st.session_state: st.session_state[k] = True
        if st.checkbox(" | ".join(f"{c}:{row[c]}" for c in cols[:4]),
                       value=st.session_state[k], key=f"chk_{idx}"):
            selected.append(idx)

    st.divider()
    st.markdown(f"### {len(selected)} contacts selected")

    if selected:
        if st.button(f"🚀 {len(selected)} contacts ko WhatsApp Bhejo!", type="primary",
                     use_container_width=True):
            errs = []
            if not ai_key:    errs.append("AI Sensy API Key missing")
            if send_img and not imgbb_key: errs.append("imgbb Key missing")
            for e in errs: st.error(e)
            if errs: st.stop()

            params_cols = [c.strip() for c in param_str.split(",") if c.strip()]
            prog = st.progress(0, text="Starting...")
            log_box = st.empty()
            logs=[]; success=failed=0

            for i,idx in enumerate(selected):
                row   = df.iloc[idx].to_dict()
                phone = normalize(str(row.get(phone_col,"")), cc)
                msg   = message
                for col in cols: msg=msg.replace("{"+str(col)+"}",str(row.get(col,"")))
                t_params = [str(row.get(c,"")) for c in params_cols]
                img_url  = ""
                prog.progress(i/len(selected), text=f"Sending {i+1}/{len(selected)}: {phone}...")
                try:
                    if send_img and imgbb_key:
                        img_url = upload_imgbb(render_image(pil,st.session_state.boxes,row), imgbb_key)
                    send_aisensy(ai_key, campaign, phone, username, t_params, img_url)
                    logs.append(f"✅ {phone}"); success+=1
                except Exception as ex:
                    logs.append(f"❌ {phone} — {ex}"); failed+=1
                log_box.code("\n".join(logs[-15:]), language=None)
                if i < len(selected)-1: time.sleep(delay_sec)

            prog.progress(1.0, text="Done!")
            if failed==0:
                st.success(f"🎉 {success} messages sent!"); st.balloons()
            else:
                st.warning(f"✅ {success} sent  |  ❌ {failed} failed")
            st.code("\n".join(logs), language=None)
