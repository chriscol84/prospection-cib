import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# Configuration de la page
st.set_page_config(page_title="CRM Prospection Partagé", layout="wide", page_icon="💼")

# --- CONNEXION GOOGLE SHEETS ---
# Note : L'URL du sheet doit être configurée dans vos secrets Streamlit
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=600) # Rafraîchissement toutes les 10 minutes
def load_data():
    # Lecture de l'onglet 'Prospection'
    df = conn.read(worksheet="Prospection")
    
    # Nettoyage des colonnes
    df.columns = [c.strip() for c in df.columns]
    
    # Formatage numérique (1 décimale)
    num_cols = ['CA (M€)', 'EBITDA (M€)', 'Dette Brute', 'Trésorerie (M€)', 'Dette Nette (M€)', 'Levier (x)']
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').round(1)
    
    return df.fillna("")

def update_gsheet(df):
    # Écriture vers Google Sheets
    conn.update(worksheet="Prospection", data=df)
    st.cache_data.clear()
    st.success("✅ Google Sheet mis à jour pour toute l'équipe !")

# --- LOGIQUE DE L'APPLICATION ---
df = load_data()

if df is not None:
    st.title("💼 CRM Prospection Christophe & Team")
    
    # --- FILTRES ---
    st.sidebar.header("🔍 Filtres")
    nom_col = "Nom de l'entité"
    search = st.sidebar.text_input("Rechercher une société", "")
    
    prio_options = sorted(list(df['Priorité'].unique()))
    selected_prio = st.sidebar.multiselect("Priorité", prio_options, default=prio_options)

    # Application des filtres
    mask = (df[nom_col].str.contains(search, case=False)) & (df['Priorité'].isin(selected_prio))
    filtered_df = df[mask]

    # --- AFFICHAGE PRINCIPAL ---
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    # --- FORMULAIRE DE MODIFICATION ---
    if not filtered_df.empty:
        st.divider()
        st.subheader("📝 Mise à jour des données")
        
        selected_company = st.selectbox("Choisir la société à modifier :", filtered_df[nom_col].tolist())
        idx = df[df[nom_col] == selected_company].index[0]
        row = df.loc[idx]

        with st.form("edit_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                # Statuts avec logique de priorité
                status_options = ["À contacter", "En veille", "Rien à faire", "Contacté", "RDV fixé", "En cours", "Gagné"]
                curr_status = str(row['Statut Follow-up'])
                
                # Correction automatique si vide selon vos règles
                if curr_status in ["", "nan"]:
                    prio = str(row['Priorité'])
                    if prio == "P1": curr_status = "À contacter"
                    elif prio == "P2": curr_status = "En veille"
                    elif prio == "P3": curr_status = "Rien à faire"
                
                new_status = st.selectbox("Statut Follow-up", status_options, 
                                          index=status_options.index(curr_status) if curr_status in status_options else 0)
                
                new_contact = st.text_input("Contact", value=str(row.get('Personne de contact', '')))

            with col2:
                new_comm = st.text_area("Commentaires / CR", value=str(row.get('Commentaires', '')))

            if st.form_submit_button("💾 Enregistrer pour l'équipe"):
                df.at[idx, 'Statut Follow-up'] = new_status
                df.at[idx, 'Commentaires'] = new_comm
                df.at[idx, 'Personne de contact'] = new_contact
                
                update_gsheet(df)
                st.rerun()