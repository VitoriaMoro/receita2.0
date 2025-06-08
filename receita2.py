import streamlit as st
import requests
from PIL import Image
import io

st.set_page_config(
    page_title="ChefAI - Encontre Receitas",
    page_icon="🍳",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ========================================================================
# Funções auxiliares
# ========================================================================

# Função para buscar receitas por ingredientes
def get_recipes_by_matching_ingredients(user_ingredients, area=None, max_recipes=10):
    recipe_ids = set()
    user_ingredients_lower = [ing.lower() for ing in user_ingredients]
    
    for ingredient in user_ingredients_lower:
        try:
            response = requests.get(
                f"https://www.themealdb.com/api/json/v1/1/filter.php?i={ingredient.strip()}"
            )
            data = response.json()
            if data.get('meals'):
                for meal in data['meals']:
                    recipe_ids.add(meal['idMeal'])
        except (requests.exceptions.RequestException, TypeError):
            continue

    if not recipe_ids:
        return []

    recipes = []
    
    for recipe_id in list(recipe_ids)[:200]:
        try:
            response = requests.get(
                f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe_id}"
            )
            recipe_data = response.json()['meals'][0]
            
            # Filtro por país/área
            if area and area != "All" and recipe_data.get('strArea') != area:
                continue
                
            recipe_ingredients = []
            for i in range(1, 21):
                ingredient_key = f'strIngredient{i}'
                if recipe_data.get(ingredient_key) and recipe_data[ingredient_key].strip():
                    ingredient = recipe_data[ingredient_key].strip().lower()
                    recipe_ingredients.append(ingredient)
            
            matches = sum(1 for ing in recipe_ingredients if ing in user_ingredients_lower)
            total_ingredients = len(recipe_ingredients)
            
            recipes.append({
                'data': recipe_data,
                'ingredients': recipe_ingredients,
                'matches': matches,
                'total': total_ingredients
            })
        
        except (requests.exceptions.RequestException, KeyError, IndexError, TypeError):
            continue

    recipes.sort(key=lambda x: x['matches'], reverse=True)
    return recipes[:max_recipes]

# Função para buscar receitas por país
def get_recipes_by_area(area):
    try:
        response = requests.get(
            f"https://www.themealdb.com/api/json/v1/1/filter.php?a={area}"
        )
        data = response.json()
        return data.get('meals', [])[:5]  # Retorna até 5 receitas
    except requests.exceptions.RequestException:
        return []

# Função para buscar lista de países
def get_areas():
    try:
        response = requests.get(
            "https://www.themealdb.com/api/json/v1/1/list.php?a=list"
        )
        data = response.json()
        return ["All"] + sorted([area['strArea'] for area in data['meals']])
    except requests.exceptions.RequestException:
        return ["All"]

# Função para exibir receitas
def display_recipe(recipe, user_ingredients, is_main=False):
    recipe_data = recipe['data']
    recipe_id = recipe_data['idMeal']
    
    # Destacar mais o nome da receita
    title_html = f"<h3 style='font-size:24px; margin-bottom:10px;'>{recipe_data['strMeal']}</h3>"
    st.markdown(title_html, unsafe_allow_html=True)
    
    with st.expander("", expanded=is_main):
        # Exibir imagem da receita com tamanho reduzido
        if recipe_data.get('strMealThumb'):
            try:
                response_img = requests.get(recipe_data['strMealThumb'])
                img = Image.open(io.BytesIO(response_img.content))
                
                # Reduzir o tamanho da imagem
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.image(img, caption=recipe_data['strMeal'], width=300)
            except:
                st.warning("Não foi possível carregar a imagem da receita")


        # Informações básicas
        st.caption(f"🎯 Compatibilidade: {recipe['matches']}/{recipe['total']} ingredientes")
        st.progress(recipe['matches'] / recipe['total'])
        st.caption(f"🗂️ Categoria: {recipe_data.get('strCategory', 'N/A')}")
        st.caption(f"🌍 Cozinha: {recipe_data.get('strArea', 'N/A')}")
        
        # Sistema de avaliação
        current_rating = st.session_state.user_ratings.get(recipe_id, 0)
        new_rating = st.slider(
            "Avalie esta receita:", 
            1, 5, current_rating,
            key=f"rate_{recipe_id}_{is_main}"
        )
        
        if st.button("Salvar Avaliação", key=f"btn_rate_{recipe_id}_{is_main}"):
            st.session_state.user_ratings[recipe_id] = new_rating
            st.success("Avaliação salva com sucesso!")
            st.experimental_rerun()
        
        # Links
        col1, col2 = st.columns(2)
        if recipe_data.get('strSource'):
            col1.markdown(f"🔗 [Receita Original]({recipe_data['strSource']})")
        if recipe_data.get('strYoutube'):
            col2.markdown(f"📺 [Vídeo no YouTube]({recipe_data['strYoutube']})")
        
        # Ingredientes
        st.subheader("📋 Ingredientes:")
        for ing in recipe['ingredients']:
            match_indicator = "✅" if ing in [i.lower() for i in user_ingredients] else "❌"
            st.markdown(f"{match_indicator} {ing.capitalize()}")
        
        # Instruções
        st.subheader("👩‍🍳 Instruções:")
        st.write(recipe_data['strInstructions'])

# ========================================================================
# Inicialização do aplicativo
# ========================================================================

# Inicializar estados da sessão
if 'saved_main_recipes' not in st.session_state:
    st.session_state.saved_main_recipes = []
    
if 'user_ratings' not in st.session_state:
    st.session_state.user_ratings = {}
    
if 'show_random_recipes' not in st.session_state:
    st.session_state.show_random_recipes = False

# ========================================================================
# Interface Principal
# ========================================================================
st.title("🍳 Experiência Chef - Descubra Receitas por Ingredientes ou País")
st.markdown("Encontre receitas perfeitas usando seus ingredientes ou explore novas culturas culinárias!")

# Barra lateral 
with st.sidebar:
    st.header("📚 Receitas Principais Salvas")
    st.caption("Suas últimas receitas principais pesquisadas")
    
    if not st.session_state.saved_main_recipes:
        st.info("Nenhuma receita salva ainda. Faça uma busca para começar!")
    else:
        for i, recipe in enumerate(st.session_state.saved_main_recipes):
            with st.expander(f"{i+1}. {recipe['data']['strMeal']}"):
                st.caption(f"Compatibilidade: {recipe['matches']}/{recipe['total']}")
                st.caption(f"🗂️ {recipe['data'].get('strCategory', 'N/A')}")
                st.caption(f"🌍 {recipe['data'].get('strArea', 'N/A')}")
                
                # Mostrar avaliação do usuário se existir
                recipe_id = recipe['data']['idMeal']
                if recipe_id in st.session_state.user_ratings:
                    rating = st.session_state.user_ratings[recipe_id]
                    st.caption(f"⭐ Sua avaliação: {rating}/5")
                
                if st.button("Ver Receita Completa", key=f"view_{i}"):
                    st.session_state.selected_recipe = recipe
                
                if st.button("Remover", key=f"remove_{i}"):
                    st.session_state.saved_main_recipes.pop(i)
                    st.experimental_rerun()
    
    st.markdown("---")
    st.header("🌍 Descubra por País")
    selected_country = st.selectbox("Escolha um país:", get_areas())
    
    if st.button("Mostrar Receitas Típicas"):
        st.session_state.show_random_recipes = True
        st.session_state.country_recipes = get_recipes_by_area(selected_country)
        st.session_state.selected_country = selected_country

# ========================================================================
# Seção de Descoberta por País
# ========================================================================
if st.session_state.get('show_random_recipes', False):
    st.subheader(f"🍜 Receitas Típicas de {st.session_state.selected_country}")
    
    if not st.session_state.get('country_recipes'):
        st.warning(f"Não encontramos receitas de {st.session_state.selected_country}.")
    else:
        for recipe in st.session_state.country_recipes:
            with st.expander(f"🍲 {recipe['strMeal']}", expanded=True):
                try:
                    # Buscar detalhes completos da receita
                    response = requests.get(
                        f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe['idMeal']}"
                    )
                    recipe_data = response.json()['meals'][0]
                    recipe_id = recipe_data['idMeal']
                    
                    # Exibir imagem
                    if recipe_data.get('strMealThumb'):
                        try:
                            response_img = requests.get(recipe_data['strMealThumb'])
                            img = Image.open(io.BytesIO(response_img.content))
                            st.image(img, caption=recipe_data['strMeal'], use_container_width=True)  # Corrigido aqui
                        except:
                            st.warning("Não foi possível carregar a imagem da receita")
                    
                    # Informações básicas
                    st.caption(f"🗂️ Categoria: {recipe_data.get('strCategory', 'N/A')}")
                    st.caption(f"🌍 Cozinha: {recipe_data.get('strArea', 'N/A')}")
                    
                    # Ingredientes
                    st.subheader("📋 Ingredientes:")
                    for i in range(1, 21):
                        ingredient = recipe_data.get(f'strIngredient{i}', '').strip()
                        measure = recipe_data.get(f'strMeasure{i}', '').strip()
                        if ingredient:
                            st.markdown(f"- {measure} {ingredient}")
                    
                    # Instruções
                    st.subheader("👩‍🍳 Instruções:")
                    st.write(recipe_data['strInstructions'])
                    
                    # Sistema de avaliação
                    current_rating = st.session_state.user_ratings.get(recipe_id, 0)
                    
                    new_rating = st.slider(
                        "Avalie esta receita:",
                        1, 5, current_rating,
                        key=f"rate_{recipe_id}"
                    )
                    
                    if st.button("Salvar Avaliação", key=f"save_{recipe_id}"):
                        st.session_state.user_ratings[recipe_id] = new_rating
                        st.success("Avaliação salva com sucesso!")
                        st.experimental_rerun()
                    
                    # Links
                    col1, col2 = st.columns(2)
                    if recipe_data.get('strSource'):
                        col1.markdown(f"🔗 [Receita Original]({recipe_data['strSource']})")
                    if recipe_data.get('strYoutube'):
                        col2.markdown(f"📺 [Vídeo no YouTube]({recipe_data['strYoutube']})")
                        
                except (requests.exceptions.RequestException, KeyError, IndexError):
                    st.error("Erro ao carregar detalhes da receita.")

# ========================================================================
# Seção Principal - Busca por Ingredientes
# ========================================================================
st.subheader("🔍 Buscar por Ingredientes")
user_input = st.text_input(
    "Digite seus ingredientes em inglês (separados por vírgula):",
    placeholder="Ex: ovo, farinha, açúcar",
    key="ingredient_input"
)

# Filtro de país para busca por ingredientes
country_filter = st.selectbox("Filtrar por país (opcional):", get_areas())

if st.button("Buscar Receitas") or user_input:
    if not user_input:
        st.warning("Por favor, digite pelo menos um ingrediente!")
        st.stop()
    
    user_ingredients = [ing.strip() for ing in user_input.split(',') if ing.strip()]
    
    with st.spinner("Procurando receitas incríveis para você..."):
        recipes = get_recipes_by_matching_ingredients(user_ingredients, country_filter)
    
    if not recipes:
        st.error("Nenhuma receita encontrada com esses ingredientes. Tente outros ingredientes!")
    else:
        # Salva a receita principal na session state
        main_recipe = recipes[0]
        if main_recipe not in st.session_state.saved_main_recipes:
            st.session_state.saved_main_recipes.insert(0, main_recipe)
        st.session_state.saved_main_recipes = st.session_state.saved_main_recipes[:10]
        
        st.success(f"🔍 Encontradas {len(recipes)} receitas!")
        
        # Mostra a receita principal
        st.subheader("🥇 Receita Principal")
        display_recipe(main_recipe, user_ingredients, is_main=True)
        
        # Mostra mais duas opções
        if len(recipes) > 1:
            st.subheader("🥈 Outras Opções")
            cols = st.columns(2)
            
            for idx in range(1, min(3, len(recipes))):
                with cols[idx-1]:
                    display_recipe(recipes[idx], user_ingredients)

# ========================================================================
# Mostrar receita selecionada da barra lateral
# ========================================================================
if 'selected_recipe' in st.session_state:
    st.subheader("📖 Receita Selecionada")
    recipe = st.session_state.selected_recipe
    recipe_data = recipe['data']
    recipe_id = recipe_data['idMeal']
    
    # Exibir imagem
    if recipe_data.get('strMealThumb'):
        try:
            response_img = requests.get(recipe_data['strMealThumb'])
            img = Image.open(io.BytesIO(response_img.content))
            st.image(img, caption=recipe_data['strMeal'], use_container_width=True)  # Corrigido aqui
        except:
            st.warning("Não foi possível carregar a imagem da receita")
    
    st.subheader(f"🍳 {recipe_data['strMeal']}")
    st.caption(f"🎯 Compatibilidade: {recipe['matches']}/{recipe['total']} ingredientes")
    st.progress(recipe['matches'] / recipe['total'])
    
    # Avaliação existente
    if recipe_id in st.session_state.user_ratings:
        st.subheader(f"⭐ Sua Avaliação: {st.session_state.user_ratings[recipe_id]}/5")
    
    # Sistema de avaliação
    current_rating = st.session_state.user_ratings.get(recipe_id, 0)
    new_rating = st.slider(
        "Atualize sua avaliação:", 
        1, 5, current_rating,
        key=f"rate_selected_{recipe_id}"
    )
    
    if st.button("Salvar Avaliação", key=f"btn_rate_selected_{recipe_id}"):
        st.session_state.user_ratings[recipe_id] = new_rating
        st.success("Avaliação atualizada com sucesso!")
        st.experimental_rerun()
    
    # Links
    col1, col2 = st.columns(2)
    if recipe_data.get('strSource'):
        col1.markdown(f"🔗 [Receita Original]({recipe_data['strSource']})")
    if recipe_data.get('strYoutube'):
        col2.markdown(f"📺 [Vídeo no YouTube]({recipe_data['strYoutube']})")
    
    # Ingredientes
    st.subheader("📋 Ingredientes:")
    for ing in recipe['ingredients']:
        st.markdown(f"• {ing.capitalize()}")
    
    # Instruções
    st.subheader("👩‍🍳 Instruções:")
    st.write(recipe_data['strInstructions'])
    
    # Metadados
    st.caption(f"🗂️ Categoria: {recipe_data.get('strCategory', 'N/A')}")
    st.caption(f"🌍 Cozinha: {recipe_data.get('strArea', 'N/A')}")
    
    # Botão para voltar
    if st.button("Voltar para os resultados"):
        del st.session_state.selected_recipe

# ========================================================================
# Rodapé
# ========================================================================
st.markdown("---")
st.markdown("Desenvolvido usando [TheMealDB API](https://www.themealdb.com/)")
