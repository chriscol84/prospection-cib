import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE L'INTERFACE ---
st.set_page_config(
    page_title="CRM Prospection Christophe", 
    layout="wide", 
    page_icon="💼"
)

# --- 2. INITIALISATION DE L'IA (MODE DEEP SEARCH ACTIF) ---
# On utilise le moteur de recherche Google en temps réel pour trouver CA, Dette et Trésorerie
model = None
selected_model_name = "Initialisation..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Détection du meilleur modèle disponible sur votre quota (6 RPM)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if models:
            best_m = next((m for m in models if "2.0" in m or "1.5" in m), models[0])
            # ACTIVATION DE LA RECHERCHE WEB FINANCIÈRE
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model_name = best_m
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# --- 3. CHARGEMENT ET MAPPING DES DONNÉES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    # Lecture de l'onglet "Prospection"
    data = conn.read(worksheet="Prospection")
    # Nettoyage des espaces en début/fin de titre pour éviter les erreurs
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

# --- CONFIGURATION DES COLONNES (Mapping exact de votre structure) ---
# On utilise ici vos noms de colonnes fournis lors de notre premier échange
COL_NOM = "Nom (FR) (Dénomination sociale)"
COL_CA = "CA (M€) (Chiffre d'affaires)"
COL_EBITDA = "EBITDA (M€) (Rentabilité opérationnelle)"
COL_DETTE = "Dette Financière Brute (Endettement total)"
COL_CASH = "Trésorerie (M€) (Liquidités)"
COL_PRIO = "Priorité (P1-P3)"
COL_ACTU = "Dernière Actualité (Signal faible / M&A / News)"
COL_ESG = "Controverses (ESG) (Risques identifiés)"
COL_ANGLE = "Angle d'Attaque (Trade Finance, Refi, Acquisition Finance)"

# Vérification de sécurité pour le nom de l'entreprise
if COL_NOM not in df.columns:
    st.error(f"❌ La colonne '{COL_NOM}' est introuvable dans votre Google Sheet.")
    with st.expander("Cliquez pour voir les colonnes détectées par le système"):
        st.write(df.columns.tolist())
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE UTILISATEUR ---
st.title("💼 CRM CIB Intelligence - Christophe")
st.caption(f"🤖 Moteur : `{selected_model_name}` | Grounding : Google Search Enabled")

# Sidebar : Filtres et Actions
st.sidebar.header("Navigation")
search_query = st.sidebar.text_input("🔍 Rechercher une société", "")
if st.sidebar.button("♻️ Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

# Filtrage dynamique
mask = df[COL_NOM].str.contains(search_query, case=False, na=False)
filtered_df = df[mask]

# Tableau de bord principal (vue simplifiée)
st.subheader("📋 Liste des cibles identifiées")
cols_to_show = [COL_NOM, COL_PRIO, COL_CA, "Secteur & Segment (Industrie)"]
st.dataframe(
    filtered_df[[c for c in cols_to_show if c in df.columns]], 
    use_container_width=True, 
    hide_index=True
)

if not filtered_df.empty:
    st.divider()
    
    # --- 6. FORMULAIRE D'ACTION ET ÉDITION ---
    selected_target = st.selectbox("🎯 Sélectionner une société pour analyse :", filtered_df[COL_NOM].tolist())
    idx = df[df[COL_NOM] == selected_target].index[0]
    row = df.loc[idx]

    st.subheader(f"📝 Gestion de : {selected_target}")
    edit_col1, edit_col2 = st.columns(2)
    
    with edit_col1:
        # Gestion de la priorité (P1-P3)
        prio_list = ["P1", "P2", "P3"]
        current_prio = str(row.get(COL_PRIO, "P3")).strip().upper()
        prio_idx = prio_list.index(current_prio) if current_prio in prio_list else 2
        new_prio = st.selectbox("Définir la priorité :", prio_list, index=prio_idx)

    with edit_col2:
        # Note libre
        new_note = st.text_area("Notes de prospection :", value=str(row.get("Accroche Personnalisée (Ice breaker ciblé)", "")))

    if st.button("💾 Enregistrer les modifications"):
        df.at[idx, COL_PRIO] = new_prio
        df.at[idx, "Accroche Personnalisée (Ice breaker ciblé)"] = new_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Modifications enregistrées !")
        st.rerun()

    # --- 7. DEEP SEARCH : RECHERCHE FINANCIÈRE ET WEB ---
    st.divider()
    st.subheader("🤖 Deep Search : Analyse financière & Signaux faibles")
    
    # Respect du quota 6 RPM
    time_diff = (datetime.now() - st.session_state.last_request_time).total_seconds()
    wait_needed = max(0, 11.5 - time_diff)

    if st.button(f"🚀 Lancer la recherche web pour {selected_target}"):
        if wait_needed > 0:
            st.warning(f"⏳ Respect du quota : veuillez patienter {int(wait_needed)}s.")
        elif model is None:
            st.error("L'IA n'est pas configurée correctement.")
        else:
            with st.status("Recherche web en cours (Rapports 2024-2025)...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                
                # Prompt expert pour forcer l'IA à trouver les chiffres manquants
                prompt_expert = f"""
                En tant qu'analyste CIB, effectue une recherche web sur {selected_target}. 
                Trouve les données financières les plus récentes (CA, EBITDA, Dette, Cash).
                Réponds EXCLUSIVEMENT en JSON avec ce format :
                {{
                    "ca": "valeur CA en M€",
                    "ebitda": "valeur EBITDA en M€",
                    "dette": "dette brute en M€",
                    "cash": "trésorerie en M€",
                    "esg": "résumé risques ESG",
                    "actu": "dernière news financière/M&A",
                    "angle": "angle d'attaque commercial"
                }}
                Si un chiffre est introuvable, mets 0. Sois précis et factuel.
                """
                
                try:
                    response = model.generate_content(prompt_expert)
                    raw_json = response.text[response.text.find('{'):response.text.rfind('}')+1]
                    res = json.loads(raw_json)
                    
                    # Mise à jour des colonnes (On écrase les N/A par les chiffres trouvés)
                    df.at[idx, COL_CA] = res.get('ca', row.get(COL_CA))
                    df.at[idx, COL_EBITDA] = res.get('ebitda', row.get(COL_EBITDA))
                    df.at[idx, COL_DETTE] = res.get('dette', row.get(COL_DETTE))
                    df.at[idx, COL_CASH] = res.get('cash', row.get(COL_CASH))
                    df.at[idx, COL_ESG] = res.get('esg', '')
                    df.at[idx, COL_ACTU] = res.get('actu', '')
                    df.at[idx, COL_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données récupérées et Sheet actualisé !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de l'analyse : {e}")

    # --- 8. FICHE DE SYNTHÈSE QUALITATIVE (TABLEAU DE BORD) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_target}")
    
    card1, card2, card3 = st.columns(3)
    
    with card1:
        st.markdown("### 💰 Finances (Live)")
        st.metric("Chiffre d'Affaires", f"{row.get(COL_CA, 'N/A')} M€")
        st.metric("EBITDA", f"{row.get(COL_EBITDA, 'N/A')} M€")
        st.write(f"**Dette Brute :** {row.get(COL_DETTE, 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get(COL_CASH, 'N/A')} M€")

    with card2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.info(f"**Risques/ESG :** {row.get(COL_ESG, 'Aucune donnée')}")
        st.write(f"**Secteur :** {row.get('Secteur & Segment (Industrie)', 'N/A')}")
        st.write(f"**Maison Mère :** {row.get('Siège & Maison-mère (Localisation du décisionnaire)', 'N/A')}")

    with card3:
        st.markdown("### 🎯 Approche CIB")
        st.success(f"**Angle d'Attaque :** {row.get(COL_ANGLE, 'À définir')}")
        st.write(f"**Dernière News :** {row.get(COL_ACTU, 'N/A')}")
        st.write(f"**Priorité :** {row.get(COL_PRIO, 'P3')}")