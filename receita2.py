import streamlit as st
import requests
from PIL import Image
import io
from deep_translator import GoogleTranslator 
import concurrent.futures
import time
from functools import lru_cache

# Configuração do tradutor com cache
@lru_cache(maxsize=1000)
def cached_translator_pt_en(text):
    return GoogleTranslator(source='pt', target='en').translate(text)

@lru_cache(maxsize=1000)
def cached_translator_en_pt(text):
    return GoogleTranslator(source='en', target='pt').translate(text)

translator_pt_en = cached_translator_pt_en
translator_en_pt = cached_translator_en_pt

session = requests.Session()

# Cache para requisições de API
@lru_cache(maxsize=500)
def cached_api_request(url):
    try:
        response = session.get(url, timeout=10)
        return response.json()
    except:
        return None

# Função para traduzir dados de receitas (otimizada)
def translate_recipe_data(recipe_data):
    try:
        # Tradução em batch para campos principais
        fields_to_translate = [
            recipe_data.get('strMeal', ''),
            recipe_data.get('strCategory', ''),
            recipe_data.get('strArea', ''),
            recipe_data.get('strInstructions', '')
        ]
        
        # Traduz todos os campos principais de uma vez
        translated_fields = GoogleTranslator(source='en', target='pt').translate_batch(fields_to_translate)
        
        recipe_data['strMeal'] = translated_fields[0]
        recipe_data['strCategory'] = translated_fields[1]
        recipe_data['strArea'] = translated_fields[2]
        recipe_data['strInstructions'] = translated_fields[3]
        
        # Traduz e ajusta medidas
        for i in range(1, 21):
            ingredient_key = f'strIngredient{i}'
            measure_key = f'strMeasure{i}'
            
            if recipe_data.get(ingredient_key) and recipe_data[ingredient_key].strip():
                recipe_data[ingredient_key] = translator_en_pt(recipe_data[ingredient_key])
            
            if recipe_data.get(measure_key) and recipe_data[measure_key].strip():
                measure_text = translator_en_pt(recipe_data[measure_key])
                
                # Aplica substituições de unidades
                replacements = {
                    'tbs': 'colher de sopa',
                    'TBS': 'colher de sopa',
                    'TBSP': 'colheres de sopa',
                    'Tbsp': 'colheres de sopa',
                    'tbsp': 'colheres de sopa',
                    'tsp': 'colher de chá',
                    'TSP': 'colher de chá',
                    'cup': 'xícara',
                    'cups': 'xícaras',
                    'Tblsp': 'colheres de sopa',
                    'TBLSP': 'colheres de sopa',
                    'ounce': 'onça',
                    'ounces': 'onças',
                    'pound': 'libra',
                    'pounds': 'libras',
                    'kg': 'kg',
                    'g': 'g',
                    'ml': 'ml',
                    'liter': 'litro',
                    'l': 'l'
                }
                
                for eng, pt in replacements.items():
                    measure_text = measure_text.replace(eng, pt)
                
                recipe_data[measure_key] = measure_text
                
        return recipe_data
    except Exception as e:
        st.error(f"Erro na tradução: {e}")
        return recipe_data

# Função para buscar detalhes de uma receita (usada no paralelismo)
def fetch_recipe_details(recipe_id):
    try:
        response = cached_api_request(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe_id}")
        if not response or 'meals' not in response or not response['meals']:
            return None
            
        recipe_data = response['meals'][0]
        return recipe_id, recipe_data
    except:
        return None

# Função para buscar receitas por ingredientes (otimizada)
def get_recipes_by_matching_ingredients(user_ingredients, area=None, max_recipes=10):
    # Traduz ingredientes para inglês
    translated_ingredients = [translator_pt_en(ing.lower().strip()) for ing in user_ingredients]
    
    recipe_ids = set()
    for ingredient in translated_ingredients:
        data = cached_api_request(f"https://www.themealdb.com/api/json/v1/1/filter.php?i={ingredient}")
        if data and data.get('meals'):
            for meal in data['meals']:
                recipe_ids.add(meal['idMeal'])

    if not recipe_ids:
        return []

    # Busca paralela de detalhes das receitas
    recipes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_id = {executor.submit(fetch_recipe_details, rid): rid for rid in list(recipe_ids)[:50]}
        for future in concurrent.futures.as_completed(future_to_id):
            result = future.result()
            if result:
                recipe_id, recipe_data = result
                # Verifica se já está no cache global
                if recipe_id in st.session_state.all_recipes_data:
                    recipe_obj = st.session_state.all_recipes_data[recipe_id]
                    if not area or area == "Todos" or recipe_obj['data'].get('strArea') == area:
                        recipes.append(recipe_obj)
                else:
                    # Processa nova receita
                    recipe_data = translate_recipe_data(recipe_data)
                    
                    if area and area != "Todos" and recipe_data.get('strArea') != area:
                        continue
                    
                    recipe_ingredients = []
                    for i in range(1, 21):
                        ingredient_key = f'strIngredient{i}'
                        if recipe_data.get(ingredient_key) and recipe_data[ingredient_key].strip():
                            ingredient = recipe_data[ingredient_key].strip().lower()
                            recipe_ingredients.append(ingredient)
                    
                    # Algoritmo de matching melhorado
                    user_ing_lower = [ing.lower() for ing in user_ingredients]
                    matches = 0
                    for ing in recipe_ingredients:
                        # Verifica correspondência parcial e sinônimos comuns
                        if any(orig_ing in ing for orig_ing in user_ing_lower) or \
                           any(ing in orig_ing for orig_ing in user_ing_lower):
                            matches += 1
                    
                    total_ingredients = len(recipe_ingredients)
                    
                    recipe_object = {
                        'data': recipe_data,
                        'ingredients': recipe_ingredients,
                        'matches': matches,
                        'total': total_ingredients
                    }
                    recipes.append(recipe_object)
                    st.session_state.all_recipes_data[recipe_id] = recipe_object

    # Ordena por compatibilidade e limita resultados
    recipes.sort(key=lambda x: (x['matches']/x['total'], x['matches']), reverse=True)
    return recipes[:max_recipes]

# Função para buscar receitas por país
def get_recipes_by_area(area):
    try:
        response = session.get(
            f"https://www.themealdb.com/api/json/v1/1/filter.php?a={area}"
        )
        data = response.json()
        if not data.get('meals'):
            return []
            
        # Obtém detalhes completos e traduz cada receita
        detailed_recipes = []
        for meal in data['meals'][:5]:
            recipe_response = session.get(
                f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal['idMeal']}"
            )
            recipe_data = recipe_response.json()['meals'][0]
            detailed_recipes.append(translate_recipe_data(recipe_data))
        
        return detailed_recipes
    except requests.exceptions.RequestException:
        return []

# Função para buscar lista de países (traduzida)
def get_areas():
    try:
        response = session.get(
            "https://www.themealdb.com/api/json/v1/1/list.php?a=list"
        )
        data = response.json()
        areas = ["Todos"] + sorted([area['strArea'] for area in data['meals']])
        
        # Traduz nomes dos países
        translated_areas = ["Todos"]
        for area in areas[1:]:
            try:
                translated_areas.append(translator_en_pt(area))
            except:
                translated_areas.append(area)
                
        return translated_areas
    except requests.exceptions.RequestException:
        return ["Todos"]

# Função para exibir receitas
def display_recipe(recipe, user_ingredients, is_main=False):
    recipe_data = recipe['data']
    recipe_id = recipe_data['idMeal']

    title_html = f"<h3 style='font-size:24px; margin-bottom:10px;'>{recipe_data['strMeal']}</h3>"
    st.markdown(title_html, unsafe_allow_html=True)

    with st.expander("", expanded=is_main):
        if recipe_data.get('strMealThumb'):
            try:
                response_img = requests.get(recipe_data['strMealThumb'])
                img = Image.open(io.BytesIO(response_img.content))
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.image(img, caption=recipe_data['strMeal'], width=240)
            except:
                st.warning("Não foi possível carregar a imagem da receita")

        st.caption(f"🎯 Compatibilidade: {recipe['matches']}/{recipe['total']} ingredientes")
        st.progress(recipe['matches'] / recipe['total'])
        st.caption(f"🗂️ Categoria: {recipe_data.get('strCategory', 'N/A')}")
        st.caption(f"🌍 Cozinha: {recipe_data.get('strArea', 'N/A')}")

        col1, col2 = st.columns(2)
        if recipe_data.get('strSource'):
            col1.markdown(f"🔗 [Receita Original]({recipe_data['strSource']})")
        if recipe_data.get('strYoutube'):
            col2.markdown(f"📺 [Vídeo no YouTube]({recipe_data['strYoutube']})")

        st.subheader("📋 Ingredientes:")
        for ing in recipe['ingredients']:
            match_indicator = "✅" if any(orig_ing.lower() in ing for orig_ing in user_ingredients) else "❌"
            st.markdown(f"{match_indicator} {ing.capitalize()}")

        st.subheader("👩‍🍳 Instruções:")
        st.write(recipe_data['strInstructions'])
        
        current_rating = st.session_state.user_ratings.get(recipe_id, 0)
        new_rating = st.slider(
            "Avalie esta receita:",
            1, 5, current_rating,
            key=f"rate_{recipe_id}_{is_main}"
        )

        if st.button("Salvar Avaliação", key=f"btn_rate_{recipe_id}_{is_main}"):
            st.session_state.user_ratings[recipe_id] = new_rating
            st.success("Avaliação salva com sucesso!")
            st.rerun()

# Função para resetar a visualização
def go_home():
    st.session_state.show_random_recipes = False
    if 'selected_recipe' in st.session_state:
        del st.session_state.selected_recipe
    st.rerun()


# Inicialização do aplicativo

st.set_page_config(
    page_title="Experiência Chef - Encontre Receitas",
    page_icon="🍳",
    layout="centered",
    initial_sidebar_state="expanded"
    
)

if 'saved_main_recipes' not in st.session_state:
    st.session_state.saved_main_recipes = []

if 'user_ratings' not in st.session_state:
    st.session_state.user_ratings = {}

if 'show_random_recipes' not in st.session_state:
    st.session_state.show_random_recipes = False

if 'all_recipes_data' not in st.session_state:
    st.session_state.all_recipes_data = {}


# Interface

col1, col2 = st.columns([5, 1])
with col1:
    st.image("Exp Chef.png", width=500)
with col2:
    if st.button("🏠 Home", use_container_width=True):
        go_home()


st.markdown("***Cansado de não saber o que cozinhar? ou de fazer sempre as mesmas coisas?***")
st.markdown("***O Experiência Chef é a solução perfeita, um assistente culinário inteligente que transforma a maneira como você descobre e interage com a comida."
            "As possibilidades são vastas e pensadas para inspirar tanto o cozinheiro iniciante quanto o mais experiente.***")


# Barra Lateral 

with st.sidebar:
    if st.button("🏠 Voltar ao Início", use_container_width=True):
        go_home()

    st.header("🌍 Descubra Receitas por Nacionalidades")
    area_list = get_areas()
    selected_country = st.selectbox("Escolha um país:", area_list, key="country_select")

    if st.button("Mostrar Receitas Típicas"):
        st.session_state.show_random_recipes = True
        # Obtém nome original do país para a API
        try:
            if selected_country != "Todos":
                country_en = GoogleTranslator(source='pt', target='en').translate(selected_country)
            else:
                country_en = "All"
                
            st.session_state.country_recipes = get_recipes_by_area(country_en)
        except:
            st.session_state.country_recipes = []
            
        st.session_state.selected_country = selected_country
        if 'selected_recipe' in st.session_state:
            del st.session_state.selected_recipe
        st.rerun()

    st.markdown("---")
    
    st.header("📚 Receitas Pesquisadas")
    st.caption("Suas últimas receitas pesquisadas")

    if not st.session_state.saved_main_recipes:
        st.info("Nenhuma receita salva ainda. Faça uma busca!")
    else:
        for i, recipe in enumerate(st.session_state.saved_main_recipes):
            with st.expander(f"**{recipe['data']['strMeal']}**", expanded=False):
                st.caption(f"Compatibilidade: {recipe['matches']}/{recipe['total']}")
                recipe_id = recipe['data']['idMeal']
                if recipe_id in st.session_state.user_ratings:
                    rating = st.session_state.user_ratings[recipe_id]
                    st.caption(f"⭐ Sua avaliação: {rating}/5")

                if st.button("Ver Receita", key=f"view_saved_{i}"):
                    st.session_state.selected_recipe = recipe
                    st.rerun()

                if st.button("Remover", key=f"remove_saved_{i}"):
                    st.session_state.saved_main_recipes.pop(i)
                    st.rerun()

    st.markdown("---")

    st.header("⭐ Minhas Avaliações")
    if not st.session_state.user_ratings:
        st.info("Você ainda não avaliou nenhuma receita.")
    else:
        sorted_ratings = sorted(st.session_state.user_ratings.items(), key=lambda item: item[1], reverse=True)

        for recipe_id, rating in sorted_ratings:
            recipe_data_obj = st.session_state.all_recipes_data.get(recipe_id)
            if recipe_data_obj:
                with st.container():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                         st.markdown(f"{'⭐' * rating} - **{recipe_data_obj['data']['strMeal']}**")
                    with col2:
                        if st.button("Ver", key=f"view_rated_{recipe_id}", use_container_width=True):
                            st.session_state.selected_recipe = recipe_data_obj
                            st.rerun()



# 1. Mostrar Receitas de Países
if st.session_state.get('show_random_recipes', False):
    st.subheader(f"🍜 Receitas Típicas de {st.session_state.selected_country}")

    if not st.session_state.get('country_recipes'):
        st.warning(f"Não encontramos receitas de {st.session_state.selected_country}.")
    else:
        for recipe in st.session_state.country_recipes:
            title_html = f"<h3 style='font-size:22px; margin-bottom:10px;'>{recipe['strMeal']}</h3>"
            st.markdown(title_html, unsafe_allow_html=True)

            with st.expander("Ver Receita", expanded=True):
                try:
                    recipe_id = recipe['idMeal']
                    if recipe_id not in st.session_state.all_recipes_data:
                        recipe_ingredients = [recipe.get(f'strIngredient{i}', '').strip() 
                                            for i in range(1, 21) 
                                            if recipe.get(f'strIngredient{i}', '').strip()]
                        
                        st.session_state.all_recipes_data[recipe_id] = {
                            'data': recipe,
                            'ingredients': recipe_ingredients,
                            'matches': 0,
                            'total': len(recipe_ingredients)
                        }

                    if recipe.get('strMealThumb'):
                        try:
                            response_img = requests.get(recipe['strMealThumb'])
                            img = Image.open(io.BytesIO(response_img.content))
                            col1, col2, col3 = st.columns([1, 2, 1])
                            with col2:
                                st.image(img, caption=recipe['strMeal'], width=300)
                        except:
                            st.warning("Não foi possível carregar a imagem da receita.")

                    st.caption(f"🗂️ Categoria: {recipe.get('strCategory', 'N/A')}")
                    st.caption(f"🌍 Cozinha: {recipe.get('strArea', 'N/A')}")

                    st.subheader("📋 Ingredientes:")
                    for i in range(1, 21):
                        ingredient = recipe.get(f'strIngredient{i}', '').strip()
                        measure = recipe.get(f'strMeasure{i}', '').strip()
                        if ingredient:
                            st.markdown(f"- {measure} {ingredient}")

                    st.subheader("👩‍🍳 Instruções:")
                    st.write(recipe['strInstructions'])

                    current_rating = st.session_state.user_ratings.get(recipe_id, 0)
                    new_rating = st.slider("Avalie esta receita:", 1, 5, current_rating, key=f"rate_country_{recipe_id}")
                    if st.button("Salvar Avaliação", key=f"save_country_{recipe_id}"):
                        st.session_state.user_ratings[recipe_id] = new_rating
                        st.success("Avaliação salva!")
                        st.rerun()

                except (requests.exceptions.RequestException, KeyError, IndexError):
                    st.error("Erro ao carregar detalhes da receita.")

# 2. Mostrar Receita Selecionada da Barra Lateral
elif 'selected_recipe' in st.session_state:
    recipe = st.session_state.selected_recipe
    recipe_data = recipe['data']
    recipe_id = recipe_data['idMeal']

    title_html = f"<h2 style='font-size:28px; margin-bottom:15px;'>{recipe_data['strMeal']}</h2>"
    st.markdown(title_html, unsafe_allow_html=True)

    if recipe_data.get('strMealThumb'):
        try:
            response_img = requests.get(recipe_data['strMealThumb'])
            img = Image.open(io.BytesIO(response_img.content))
            col1, col2, col3 = st.columns([1, 3, 1])
            with col2:
                st.image(img, width=350)
        except:
            st.warning("Não foi possível carregar a imagem da receita")

    if 'matches' in recipe and 'total' in recipe and recipe['total'] > 0:
        st.caption(f"🎯 Compatibilidade: {recipe['matches']}/{recipe['total']} ingredientes")
        st.progress(recipe['matches'] / recipe['total'])

    if recipe_id in st.session_state.user_ratings:
        st.subheader(f"⭐ Sua Avaliação: {st.session_state.user_ratings[recipe_id]}/5")

    current_rating = st.session_state.user_ratings.get(recipe_id, 0)
    new_rating = st.slider("Atualize sua avaliação:", 1, 5, current_rating, key=f"rate_selected_{recipe_id}")

    if st.button("Salvar Avaliação", key=f"btn_rate_selected_{recipe_id}"):
        st.session_state.user_ratings[recipe_id] = new_rating
        st.success("Avaliação atualizada com sucesso!")
        st.rerun()

    col1, col2 = st.columns(2)
    if recipe_data.get('strSource'):
        col1.markdown(f"🔗 [Receita Original]({recipe_data['strSource']})")
    if recipe_data.get('strYoutube'):
        col2.markdown(f"📺 [Vídeo no YouTube]({recipe_data['strYoutube']})")

    st.subheader("📋 Ingredientes:")
    for ing in recipe['ingredients']:
        st.markdown(f"• {ing.capitalize()}")

    st.subheader("👩‍🍳 Instruções:")
    st.write(recipe_data['strInstructions'])
    st.caption(f"🗂️ Categoria: {recipe_data.get('strCategory', 'N/A')}")
    st.caption(f"🌍 Cozinha: {recipe_data.get('strArea', 'N/A')}")

# 3. Mostrar Busca por Ingredientes (Página Inicial)
else:
    st.subheader("🔍 Buscar por Ingredientes")
    user_input = st.text_input(
        "Digite seus ingredientes (separados por vírgula):",
        placeholder="Ex: frango, arroz, cebola",
        key="ingredient_input"
    )
    country_filter = st.selectbox("Filtrar por país (opcional):", get_areas(), key="country_filter")

    if st.button("Buscar Receitas"):
        if not user_input:
            st.warning("Por favor, digite pelo menos um ingrediente!")
            st.stop()

        user_ingredients = [ing.strip() for ing in user_input.split(',') if ing.strip()]
        with st.spinner("Procurando receitas incríveis para você..."):
            # Converte filtro de país para inglês se necessário
            try:
                if country_filter != "Todos":
                    country_en = GoogleTranslator(source='pt', target='en').translate(country_filter)
                else:
                    country_en = None
            except:
                country_en = None
                
            recipes = get_recipes_by_matching_ingredients(user_ingredients, country_en)

        if not recipes:
            st.error("Nenhuma receita encontrada. Tente outros ingredientes!")
        else:
            main_recipe = recipes[0]
            if main_recipe not in st.session_state.saved_main_recipes:
                st.session_state.saved_main_recipes.insert(0, main_recipe)
            st.session_state.saved_main_recipes = st.session_state.saved_main_recipes[:10]

            st.success(f"🔍 Encontradas {len(recipes)} receitas!")
            st.subheader("🥇 Receita Principal")
            display_recipe(main_recipe, user_ingredients, is_main=True)

            if len(recipes) > 1:
                st.subheader("🥈 Outras Opções")
                cols = st.columns(min(2, len(recipes)-1))
                for idx in range(1, min(3, len(recipes))):
                     with cols[idx-1]:
                         display_recipe(recipes[idx], user_ingredients)
st.markdown("---")

st.markdown("***Experiência Chef: Seu Assistente de Cozinha Inteligente***")
st.markdown("O Experiência Chef é o aplicativo que transforma sua rotina na cozinha, oferecendo inspiração e praticidade."
            "Com ele, você pode:")
st.markdown("**Cozinhar com o que Tem**: Digite os ingredientes da sua despensa e encontre receitas compatíveis."
            "O app mostra um índice de aproveitamento para você escolher a melhor opção e evitar o desperdício.")
st.markdown("**Explorar a Culinária Mundial**: Viaje por sabores de diferentes países. Basta escolher uma região"
            "para descobrir e preparar pratos típicos com instruções em português.")
st.markdown("**Organizar suas Receitas Favoritas**: Crie seu livro de receitas digital. Avalie os pratos que você preparou,"
            "acesse seu histórico de buscas e tenha sempre à mão suas descobertas preferidas.")
st.markdown("Em resumo, o Experiência Chef é uma ferramenta completa que oferece inspiração, praticidade e organização."
            "Ele transforma ingredientes esquecidos em oportunidades, satisfaz a curiosidade por novas culturas e ajuda "
            "você a construir um acervo confiável de receitas que realmente funcionam para o seu paladar.")

st.markdown("---")
st.markdown("Desenvolvido usando [TheMealDB API](https://www.themealdb.com/)")
