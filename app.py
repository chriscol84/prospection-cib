import streamlit as st
import pandas as pd
import os

# Configuration de la page
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# Nom du fichier (doit être dans le même dossier que app.py)
FILE_NAME = 'Prospection_CIB_FULL_Final.csv'

@st.cache_data
def load_data():
    if not os.path.exists(FILE_NAME):
        st.error(f"Fichier '{FILE_NAME}' introuvable.")
        return None
    try:
        # Lecture avec le séparateur point-virgule
        df = pd.read_csv(FILE_NAME, sep=';', encoding='utf-8')
    except:
        df = pd.read_csv(FILE_NAME, sep=';', encoding='latin-1')
    df.columns = [c.strip() for c in df.columns]
    return df

def save_data(df):
    df.to_csv(FILE_NAME, index=False, sep=';', encoding='utf-8')
    st.success("✅ Fichier mis à jour avec succès !")

df = load_data()

if df is not None:
    # --- Barre Latérale : Recherche & Filtres ---
    st.sidebar.title("🔍 Filtres")
    search = st.sidebar.text_input("Nom de la société", "")
    
    # Filtre Priorité (P1, P2, P3)
    prio_list = ["Tous"] + sorted(df["Priorité"].dropna().unique().tolist())
    selected_prio = st.sidebar.selectbox("Niveau de Priorité", prio_list)

    # Filtrage des données
    filtered_df = df.copy()
    if search:
        filtered_df = filtered_df[filtered_df["Nom de l'entité"].str.contains(search, case=False, na=False)]
    if selected_prio != "Tous":
        filtered_df = filtered_df[filtered_df["Priorité"] == selected_prio]

    # --- Corps de l'application ---
    st.title("🚀 CRM Prospection Christophe")

    if filtered_df.empty:
        st.warning("Aucun prospect trouvé.")
    else:
        # Sélection du prospect
        company = st.selectbox("Sélectionnez une entreprise :", filtered_df["Nom de l'entité"].tolist())
        idx = df[df["Nom de l'entité"] == company].index[0]
        row = df.loc[idx]

        # Indicateurs clés
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CA (M€)", f"{row['CA (M€)']}")
        c2.metric("EBITDA (M€)", f"{row['EBITDA (M€)']}")
        c3.metric("Priorité", row['Priorité'])
        c4.metric("Potentiel", f"{row['Potentiel (1-5)']}/5")

        st.divider()

        # Onglets pour organiser l'information
        tab1, tab2, tab3 = st.tabs(["📊 Données Financières", "✍️ Suivi CRM", "🌐 Actualités"])

        with tab1:
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**Groupe :** {row['Maison Mère (Groupe)']}")
                st.write(f"**Actionnaire :** {row['Actionnaire Maj.']}")
                st.write(f"**Contact :** {row['Personne de contact']}")
                st.write(f"**Email :** {row['Email']}")
            with col_b:
                st.write(f"**Dette Nette (M€) :** {row['Dette Nette (M€)']}")
                st.write(f"**Maturité Dette :** {row['Maturité de Crédit (Source)']}")
                st.write(f"**ESG / Controverses :** {row['Controverses']}")

        with tab2:
            st.subheader("Mise à jour du statut")
            with st.form("crm_update"):
                # Liste des statuts
                options = ["À contacter", "Contacté", "RDV fixé", "En cours", "Gagné", "Stand-by"]
                current_stat = str(row['Statut Follow-up'])
                if current_stat not in options: options.append(current_stat)
                
                new_status = st.selectbox("Statut actuel", options, index=options.index(current_stat))
                new_comm = st.text_area("Commentaires", value=str(row['Commentaires']) if pd.notna(row['Commentaires']) else "")
                
                if st.form_submit_button("Sauvegarder les changements"):
                    df.at[idx, 'Statut Follow-up'] = new_status
                    df.at[idx, 'Commentaires'] = new_comm
                    save_data(df)
                    st.rerun()

        with tab3:
            st.subheader("Veille Web")
            st.info(f"**Dernière actualité enregistrée :**\n{row['Actualité Récente']}")
            
            # Bouton de recherche automatique
            search_url = f"https://www.google.com/search?q={company.replace(' ', '+')}+actualité+M&A+finance&tbm=nws"
            st.link_button(f"🔍 Chercher {company} sur Google News", search_url)
            
            # Mise à jour de la colonne actualité
            new_news = st.text_input("Mettre à jour l'actualité (coller ici) :")
            if st.button("Actualiser la news"):
                df.at[idx, 'Actualité Récente'] = new_news
                save_data(df)
                st.rerun()