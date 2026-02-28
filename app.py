import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="CRM Prospection Christophe", 
    layout="wide", 
    page_icon="💼"
)

# --- 2. INITIALISATION IA (CORRECTIF SYNTAXE 2026) ---
model = None
selected_model_name = "Scan du modèle..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Récupération automatique du meilleur modèle Flash disponible
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if available_models:
            best_m = next((m for m in available_models if "flash" in m.lower()), available_models[0])
            
            # SYNTAXE CORRECTE : 'google_search_retrieval' est le nom du champ en 2026
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model_name = best_m
    except Exception as e:
        st.error(f"Erreur d'initialisation IA : {e}")

# --- 3. CONNEXION GOOGLE SHEETS (VIA SECRETS.TOML) ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    @st.cache_data(ttl=15)
    def load_data():
        # Lecture de l'onglet nommé "Prospection"
        data = conn.read(worksheet="Prospection")
        # Nettoyage des noms de colonnes (suppression des espaces invisibles)
        data.columns = [str(c).strip() for c in data.columns]
        return data.fillna("")

    df = load_data()
except Exception as e:
    st.error(f"Erreur de connexion au Google Sheet : {e}")
    st.stop()

# --- 4. MAPPING DYNAMIQUE DES COLONNES ---
def find_column(keywords):
    """Trouve une colonne même si l'utilisateur modifie légèrement le nom dans Excel"""
    for col in df.columns:
        if any(key.lower() in col.lower() for key in keywords):
            return col
    return None

C_NOM    = find_column(["Nom (FR)", "Dénomination", "Nom"])
C_CA     = find_column(["CA (M€)", "Chiffre d'affaires", "CA"])
C_EBITDA = find_column(["EBITDA", "Rentabilité"])
C_DETTE  = find_column(["Dette Financière", "Endettement", "Dette Brute"])
C_CASH   = find_column(["Trésorerie", "Liquidités", "Cash"])
C_PRIO   = find_column(["Priorité", "P1-P3"])
C_ACTU   = find_column(["Actualité", "Signal faible", "News"])
C_ESG    = find_column(["Controverses", "ESG", "Risques"])
C_ANGLE  = find_column(["Angle", "Attaque", "Approche"])
C_SECT   = find_column(["Secteur", "Industrie"])
C_ACC    = find_column(["Accroche", "Ice breaker"])

if not C_NOM:
    st.error("❌ La colonne 'Nom (FR)' est introuvable dans votre fichier Google Sheet.")
    st.stop()

# --- 5. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_req_time" not in st.session_state:
    st.session_state.last_req_time = datetime.now() - timedelta(seconds=15)

# --- 6. INTERFACE STREAMLIT ---
st.title("🚀 CRM CIB Intelligence - Christophe")
st.info(f"Moteur IA : **{selected_model_name}** | Google Search : **Actif**")



with st.sidebar:
    st.header("Filtrage & Actions")
    search_query = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Actualiser le Sheet"):
        st.cache_data.clear()
        st.rerun()

# Filtrage du DataFrame en temps réel
mask = df[C_NOM].astype(str).str.contains(search_query, case=False, na=False)
f_df = df[mask]

st.subheader("📋 Pipeline de Prospection")
st.dataframe(f_df[[C_NOM, C_PRIO, C_CA, C_SECT]], use_container_width=True, hide_index=True)

if not f_df.empty:
    st.divider()
    target = st.selectbox("🎯 Sélectionner pour analyse :", f_df[C_NOM].tolist())
    idx = df[df[C_NOM] == target].index[0]
    row = df.loc[idx]

    # --- 7. ÉDITION MANUELLE ET SAUVEGARDE ---
    st.subheader(f"📝 Suivi de {target}")
    col1, col2 = st.columns(2)
    with col1:
        p_opts = ["P1", "P2", "P3"]
        current_prio = str(row.get(C_PRIO, "P3"))[:2].upper()
        n_prio = st.selectbox("Priorité :", p_opts, index=p_opts.index(current_prio) if current_prio in p_opts else 2)
    with col2:
        n_note = st.text_area("Accroche Personnalisée :", value=str(row.get(C_ACC, "")))

    if st.button("💾 Sauvegarder les modifications"):
        df.at[idx, C_PRIO] = n_prio
        df.at[idx, C_ACC] = n_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Modifications enregistrées dans Google Sheets !")
        st.rerun()

    # --- 8. DEEP SEARCH IA (ENRICHISSEMENT) ---
    st.divider()
    st.subheader("🤖 Intelligence Financière Deep Search")
    
    # Calcul du temps d'attente pour respecter le quota gratuit
    wait = max(0, 15.0 - (datetime.now() - st.session_state.last_req_time).total_seconds())

    if st.button(f"🚀 Lancer l'analyse web pour {target}"):
        if wait > 0:
            st.warning(f"⏳ Respect du quota : veuillez patienter {int(wait)}s.")
        elif model is None:
            st.error("L'IA n'est pas configurée. Vérifiez vos secrets.")
        else:
            with st.status(f"Recherche et analyse de {target} sur Google...", expanded=True) as status:
                st.session_state.last_req_time = datetime.now()
                prompt = f"""
                Réalise une analyse financière précise de la société {target}. 
                Réponds EXCLUSIVEMENT sous forme de JSON avec ces clés :
                {{
                    "ca": "valeur CA en M€",
                    "ebitda": "valeur EBITDA en M€",
                    "dette": "dette brute en M€",
                    "cash": "trésorerie en M€",
                    "esg": "résumé des risques ESG",
                    "actu": "dernière news financière majeure",
                    "angle": "conseil d'approche CIB (Trade Finance/Refi)"
                }}
                Si une donnée est introuvable, indique 0 pour les chiffres et 'N/A' pour le texte.
                """
                try:
                    response = model.generate_content(prompt)
                    # Nettoyage de la réponse pour extraire le JSON
                    json_text = response.text[response.text.find('{'):response.text.rfind('}')+1]
                    res = json.loads(json_text)
                    
                    # Mise à jour des colonnes dans le DataFrame local
                    for key, col in zip(['ca', 'ebitda', 'dette', 'cash'], [C_CA, C_EBITDA, C_DETTE, C_CASH]):
                        df.at[idx, col] = res.get(key, row[col])
                    
                    df.at[idx, C_ESG] = res.get('esg', '')
                    df.at[idx, C_ACTU] = res.get('actu', '')
                    df.at[idx, C_ANGLE] = res.get('angle', '')
                    
                    # Envoi au Google Sheet
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données récupérées et enregistrées !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de l'analyse : {e}")

    # --- 9. FICHE DE SYNTHÈSE VISUELLE ---
    st.divider()
    st.subheader(f"🔍 Fiche 360° : {target}")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("### 💰 Finances")
        st.metric("Chiffre d'Affaires", f"{row.get(C_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(C_EBITDA, '0')} M€")
    with f2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**Risques ESG :** {row.get(C_ESG, 'N/A')}")
        st.write(f"**Actualité :** {row.get(C_ACTU, 'N/A')}")
    with f3:
        st.markdown("### 🎯 Prospection")
        st.success(f"**Angle d'attaque :** {row.get(C_ANGLE, 'N/A')}")
        st.write(f"**Secteur :** {row.get(C_SECT, 'N/A')}")