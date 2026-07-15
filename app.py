import base64
import html
import io
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageDraw


# --------------------------------------------------
# 기본 설정
# --------------------------------------------------
st.set_page_config(
    page_title="장보기 미션 앱",
    page_icon="🛒",
    layout="wide",
)

MISSIONS = {
    "카레 만들기": {
        "emoji": "🍛",
        "budget": 20_000,
        "description": "카레를 만들 때 필요한 재료를 예산 안에서 골라 보세요.",
    },
    "여름 캠핑 준비하기": {
        "emoji": "🏕️",
        "budget": 50_000,
        "description": "여름 캠핑에 필요한 물건을 예산 안에서 준비해 보세요.",
    },
    "친구 생일파티 준비하기": {
        "emoji": "🎂",
        "budget": 35_000,
        "description": "친구의 생일파티에 필요한 물건을 예산 안에서 골라 보세요.",
    },
}


# --------------------------------------------------
# 화면 꾸미기
# --------------------------------------------------
st.markdown(
    """
    <style>
    .stApp {
        background-color: #fffaf0;
    }

    .main-title {
        text-align: center;
        font-size: 42px;
        font-weight: 800;
        color: #333333;
        margin-bottom: 10px;
    }

    .sub-title {
        text-align: center;
        font-size: 20px;
        color: #666666;
        margin-bottom: 30px;
    }

    .mission-box {
        background-color: white;
        border: 3px solid #ffd166;
        border-radius: 20px;
        padding: 22px;
        margin-bottom: 16px;
        text-align: center;
        min-height: 180px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
    }

    .mission-name {
        font-size: 26px;
        font-weight: 800;
        color: #333333;
    }

    .mission-budget {
        font-size: 22px;
        font-weight: 700;
        color: #e76f51;
        margin-top: 10px;
    }

    .product-name {
        font-size: 21px;
        font-weight: 800;
        text-align: center;
        margin-top: 8px;
    }

    .product-price {
        font-size: 19px;
        font-weight: 700;
        color: #e76f51;
        text-align: center;
        margin-bottom: 8px;
    }

    .budget-safe {
        background-color: #e8f7ee;
        border: 2px solid #52b788;
        border-radius: 15px;
        padding: 15px;
        font-size: 20px;
        font-weight: 700;
    }

    .budget-warning {
        background-color: #ffe8e8;
        border: 2px solid #e63946;
        border-radius: 15px;
        padding: 15px;
        font-size: 20px;
        font-weight: 800;
        color: #c1121f;
    }

    div.stButton > button {
        min-height: 48px;
        font-size: 18px;
        font-weight: 700;
        border-radius: 12px;
    }

    div.stDownloadButton > button {
        min-height: 55px;
        font-size: 20px;
        font-weight: 800;
        border-radius: 14px;
        background-color: #2a9d8f;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 세션 상태
# --------------------------------------------------
def initialize_session_state():
    default_values = {
        "page": "start",
        "selected_mission": None,
        "budget": 0,
        "cart": {},
        "purchase_reason": "",
    }

    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


# --------------------------------------------------
# 상품 불러오기
# --------------------------------------------------
@st.cache_data
def load_products():
    csv_path = Path("products.csv")

    if not csv_path.exists():
        st.error(
            "products.csv 파일을 찾을 수 없습니다. "
            "app.py와 같은 폴더에 products.csv 파일을 올려 주세요."
        )
        st.stop()

    try:
        products = pd.read_csv(csv_path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        products = pd.read_csv(csv_path, encoding="cp949")

    required_columns = ["품명", "가격", "이미지 url"]
    missing_columns = [
        column for column in required_columns if column not in products.columns
    ]

    if missing_columns:
        st.error(
            "products.csv에 필요한 열이 없습니다: "
            + ", ".join(missing_columns)
        )
        st.info("열 이름을 다음과 같이 작성해 주세요: 품명, 가격, 이미지 url")
        st.stop()

    products = products[required_columns].copy()

    products["품명"] = products["품명"].fillna("").astype(str).str.strip()
    products["이미지 url"] = (
        products["이미지 url"].fillna("").astype(str).str.strip()
    )

    products["가격"] = (
        products["가격"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("원", "", regex=False)
        .str.strip()
    )

    products["가격"] = pd.to_numeric(
        products["가격"],
        errors="coerce",
    )

    products = products.dropna(subset=["가격"])
    products = products[products["품명"] != ""]
    products["가격"] = products["가격"].astype(int)

    products = products.reset_index(drop=True)
    products["상품번호"] = products.index.astype(str)

    return products


products = load_products()


# --------------------------------------------------
# 공통 함수
# --------------------------------------------------
def calculate_cart_total():
    total = 0

    for item in st.session_state.cart.values():
        total += item["가격"] * item["수량"]

    return total


def select_mission(mission_name):
    st.session_state.selected_mission = mission_name
    st.session_state.budget = MISSIONS[mission_name]["budget"]
    st.session_state.cart = {}
    st.session_state.purchase_reason = ""
    st.session_state.page = "shopping"

    for key in list(st.session_state.keys()):
        if key.startswith("quantity_"):
            del st.session_state[key]


def add_to_cart(product_id, product_name, price, image_url, quantity):
    if quantity <= 0:
        return

    if product_id in st.session_state.cart:
        st.session_state.cart[product_id]["수량"] += quantity
    else:
        st.session_state.cart[product_id] = {
            "품명": product_name,
            "가격": int(price),
            "이미지 url": image_url,
            "수량": quantity,
        }


def remove_cart_item(product_id):
    if product_id in st.session_state.cart:
        del st.session_state.cart[product_id]


def reset_app():
    st.session_state.page = "start"
    st.session_state.selected_mission = None
    st.session_state.budget = 0
    st.session_state.cart = {}
    st.session_state.purchase_reason = ""

    for key in list(st.session_state.keys()):
        if key.startswith("quantity_"):
            del st.session_state[key]


# --------------------------------------------------
# 이미지 처리
# --------------------------------------------------
def make_placeholder_image():
    image = Image.new(
        "RGB",
        (500, 350),
        color=(240, 240, 240),
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (10, 10, 490, 340),
        outline=(180, 180, 180),
        width=4,
    )

    draw.line(
        (50, 300, 180, 180, 270, 260, 380, 120, 450, 300),
        fill=(180, 180, 180),
        width=8,
    )

    draw.ellipse(
        (90, 60, 170, 140),
        fill=(200, 200, 200),
    )

    return image


@st.cache_data(show_spinner=False)
def image_url_to_data_uri(image_url):
    try:
        if not image_url:
            raise ValueError("이미지 주소 없음")

        response = requests.get(
            image_url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0",
            },
        )
        response.raise_for_status()

        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        image.thumbnail((600, 400))

        background = Image.new(
            "RGB",
            (600, 400),
            color="white",
        )

        x = (600 - image.width) // 2
        y = (400 - image.height) // 2
        background.paste(image, (x, y))

    except Exception:
        background = make_placeholder_image()
        background = background.resize((600, 400))

    image_buffer = io.BytesIO()
    background.save(
        image_buffer,
        format="PNG",
        optimize=True,
    )

    encoded_image = base64.b64encode(
        image_buffer.getvalue()
    ).decode("utf-8")

    return f"data:image/png;base64,{encoded_image}"


# --------------------------------------------------
# 결과 SVG 생성
# SVG를 사용하면 한글을 이미지에 직접 그리지 않으므로
# 서버에 한글 글꼴이 없어도 글자가 깨질 가능성이 낮습니다.
# 상품 이미지도 SVG 안에 포함합니다.
# --------------------------------------------------
def wrap_text(text, max_length=34):
    text = str(text).strip()

    if not text:
        return []

    lines = []

    while len(text) > max_length:
        split_position = text.rfind(" ", 0, max_length + 1)

        if split_position == -1:
            split_position = max_length

        lines.append(text[:split_position].strip())
        text = text[split_position:].strip()

    if text:
        lines.append(text)

    return lines


def create_result_svg():
    mission_name = st.session_state.selected_mission
    budget = st.session_state.budget
    total = calculate_cart_total()
    remaining = budget - total
    reason = st.session_state.purchase_reason.strip()

    cart_items = list(st.session_state.cart.values())
    reason_lines = wrap_text(reason, max_length=38)

    item_height = 190
    reason_height = max(150, 55 + len(reason_lines) * 38)
    canvas_height = (
        300
        + len(cart_items) * item_height
        + reason_height
        + 180
    )

    svg_parts = [
        f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             xmlns:xlink="http://www.w3.org/1999/xlink"
             width="1000"
             height="{canvas_height}"
             viewBox="0 0 1000 {canvas_height}">

            <rect width="1000"
                  height="{canvas_height}"
                  fill="#fffaf0"/>

            <rect x="40"
                  y="40"
                  width="920"
                  height="{canvas_height - 80}"
                  rx="30"
                  fill="#ffffff"
                  stroke="#ffd166"
                  stroke-width="6"/>

            <text x="500"
                  y="105"
                  text-anchor="middle"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="44"
                  font-weight="800"
                  fill="#333333">
                장보기 미션 결과
            </text>

            <text x="80"
                  y="175"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="31"
                  font-weight="800"
                  fill="#264653">
                미션: {html.escape(mission_name)}
            </text>

            <rect x="70"
                  y="205"
                  width="860"
                  height="75"
                  rx="18"
                  fill="#e8f7ee"/>

            <text x="100"
                  y="253"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="26"
                  font-weight="700"
                  fill="#1b4332">
                예산 {budget:,}원
                · 사용한 금액 {total:,}원
                · 남은 돈 {remaining:,}원
            </text>
        """
    ]

    current_y = 315

    for item in cart_items:
        image_data_uri = image_url_to_data_uri(item["이미지 url"])
        item_total = item["가격"] * item["수량"]

        svg_parts.append(
            f"""
            <rect x="70"
                  y="{current_y}"
                  width="860"
                  height="160"
                  rx="20"
                  fill="#f8f9fa"
                  stroke="#dedede"
                  stroke-width="2"/>

            <image x="90"
                   y="{current_y + 15}"
                   width="190"
                   height="130"
                   preserveAspectRatio="xMidYMid meet"
                   href="{image_data_uri}"
                   xlink:href="{image_data_uri}"/>

            <text x="315"
                  y="{current_y + 55}"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="28"
                  font-weight="800"
                  fill="#333333">
                {html.escape(item["품명"])}
            </text>

            <text x="315"
                  y="{current_y + 100}"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="23"
                  fill="#555555">
                {item["가격"]:,}원 × {item["수량"]}개
            </text>

            <text x="315"
                  y="{current_y + 137}"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="24"
                  font-weight="800"
                  fill="#e76f51">
                합계 {item_total:,}원
            </text>
            """
        )

        current_y += item_height

    svg_parts.append(
        f"""
        <rect x="70"
              y="{current_y}"
              width="860"
              height="{reason_height}"
              rx="20"
              fill="#fff3cd"
              stroke="#ffd166"
              stroke-width="3"/>

        <text x="100"
              y="{current_y + 48}"
              font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
              font-size="27"
              font-weight="800"
              fill="#664d03">
            내가 이 물건을 구매한 이유
        </text>
        """
    )

    text_y = current_y + 92

    for reason_line in reason_lines:
        svg_parts.append(
            f"""
            <text x="100"
                  y="{text_y}"
                  font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
                  font-size="24"
                  fill="#333333">
                {html.escape(reason_line)}
            </text>
            """
        )
        text_y += 38

    footer_y = current_y + reason_height + 90

    svg_parts.append(
        f"""
        <text x="500"
              y="{footer_y}"
              text-anchor="middle"
              font-family="'Noto Sans KR', 'Malgun Gothic', sans-serif"
              font-size="23"
              font-weight="700"
              fill="#2a9d8f">
            예산을 생각하며 알뜰하게 장보기를 완료했습니다!
        </text>

        </svg>
        """
    )

    return "".join(svg_parts).encode("utf-8")


# --------------------------------------------------
# 시작 화면
# --------------------------------------------------
def show_start_page():
    st.markdown(
        '<div class="main-title">🛒 장보기 미션</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-title">'
        "도전하고 싶은 미션을 선택해 주세요!"
        "</div>",
        unsafe_allow_html=True,
    )

    mission_columns = st.columns(3)

    for column, (mission_name, mission_info) in zip(
        mission_columns,
        MISSIONS.items(),
    ):
        with column:
            st.markdown(
                f"""
                <div class="mission-box">
                    <div style="font-size:60px;">
                        {mission_info["emoji"]}
                    </div>
                    <div class="mission-name">
                        {mission_name}
                    </div>
                    <div class="mission-budget">
                        예산 {mission_info["budget"]:,}원
                    </div>
                    <div style="margin-top:12px; color:#666666;">
                        {mission_info["description"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                f"{mission_name} 선택",
                key=f"select_{mission_name}",
                use_container_width=True,
                type="primary",
            ):
                select_mission(mission_name)
                st.rerun()


# --------------------------------------------------
# 쇼핑 화면
# --------------------------------------------------
def show_shopping_page():
    mission_name = st.session_state.selected_mission
    budget = st.session_state.budget

    header_col1, header_col2 = st.columns([4, 1])

    with header_col1:
        st.title(
            f'{MISSIONS[mission_name]["emoji"]} '
            f"미션: {mission_name}"
        )
        st.write(MISSIONS[mission_name]["description"])
        st.subheader(f"💰 사용할 수 있는 예산: {budget:,}원")

    with header_col2:
        if st.button(
            "미션 다시 선택",
            use_container_width=True,
        ):
            reset_app()
            st.rerun()

    st.divider()
    st.header("🛍️ 상품을 골라 보세요")

    product_columns = st.columns(3)

    for index, product in products.iterrows():
        product_id = product["상품번호"]
        quantity_key = f"quantity_{product_id}"

        if quantity_key not in st.session_state:
            st.session_state[quantity_key] = 1

        with product_columns[index % 3]:
            with st.container(border=True):
                try:
                    st.image(
                        product["이미지 url"],
                        use_container_width=True,
                    )
                except Exception:
                    st.image(
                        make_placeholder_image(),
                        use_container_width=True,
                    )

                st.markdown(
                    f'<div class="product-name">'
                    f'{html.escape(product["품명"])}'
                    f"</div>",
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f'<div class="product-price">'
                    f'{product["가격"]:,}원'
                    f"</div>",
                    unsafe_allow_html=True,
                )

                minus_column, quantity_column, plus_column = st.columns(
                    [1, 1.3, 1]
                )

                with minus_column:
                    if st.button(
                        "➖",
                        key=f"minus_{product_id}",
                        use_container_width=True,
                    ):
                        st.session_state[quantity_key] = max(
                            1,
                            st.session_state[quantity_key] - 1,
                        )
                        st.rerun()

                with quantity_column:
                    st.markdown(
                        f"""
                        <div style="
                            text-align:center;
                            font-size:24px;
                            font-weight:800;
                            padding-top:8px;
                        ">
                            {st.session_state[quantity_key]}개
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with plus_column:
                    if st.button(
                        "➕",
                        key=f"plus_{product_id}",
                        use_container_width=True,
                    ):
                        st.session_state[quantity_key] += 1
                        st.rerun()

                if st.button(
                    "🛒 장바구니 담기",
                    key=f"add_{product_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    add_to_cart(
                        product_id=product_id,
                        product_name=product["품명"],
                        price=product["가격"],
                        image_url=product["이미지 url"],
                        quantity=st.session_state[quantity_key],
                    )

                    st.toast(
                        f'{product["품명"]}을 장바구니에 담았습니다!',
                        icon="✅",
                    )
                    st.rerun()

    st.divider()
    st.header("🛒 장바구니")

    if not st.session_state.cart:
        st.info("아직 장바구니에 담은 물건이 없습니다.")
    else:
        for product_id, item in list(
            st.session_state.cart.items()
        ):
            item_total = item["가격"] * item["수량"]

            cart_image, cart_info, cart_button = st.columns(
                [1, 4, 1]
            )

            with cart_image:
                try:
                    st.image(
                        item["이미지 url"],
                        width=110,
                    )
                except Exception:
                    st.image(
                        make_placeholder_image(),
                        width=110,
                    )

            with cart_info:
                st.markdown(f"### {item['품명']}")
                st.write(
                    f"{item['가격']:,}원 × "
                    f"{item['수량']}개 = "
                    f"**{item_total:,}원**"
                )

            with cart_button:
                if st.button(
                    "삭제",
                    key=f"remove_{product_id}",
                    use_container_width=True,
                ):
                    remove_cart_item(product_id)
                    st.rerun()

            st.divider()

    total = calculate_cart_total()
    remaining = budget - total
    over_budget = total > budget

    summary_column1, summary_column2, summary_column3 = st.columns(3)

    summary_column1.metric(
        "예산",
        f"{budget:,}원",
    )

    summary_column2.metric(
        "사용 금액",
        f"{total:,}원",
    )

    summary_column3.metric(
        "남은 돈",
        f"{remaining:,}원",
    )

    if over_budget:
        st.markdown(
            f"""
            <div class="budget-warning">
                ⚠️ 예산을 {abs(remaining):,}원 초과했습니다.<br>
                장바구니에서 물건을 빼거나 수량을 줄여 주세요.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="budget-safe">
                ✅ 예산 안에서 장보고 있습니다.
                현재 {remaining:,}원이 남았습니다.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    cart_is_empty = len(st.session_state.cart) == 0

    submit_clicked = st.button(
        "📨 제출하기",
        use_container_width=True,
        type="primary",
        disabled=over_budget or cart_is_empty,
    )

    # 제출 버튼을 실제로 눌렀을 때만 결과 화면으로 이동
    if submit_clicked:
        st.session_state.page = "result"
        st.rerun()

    if cart_is_empty:
        st.caption(
            "물건을 한 개 이상 장바구니에 담아야 제출할 수 있습니다."
        )


# --------------------------------------------------
# 결과 화면
# --------------------------------------------------
def show_result_page():
    mission_name = st.session_state.selected_mission
    budget = st.session_state.budget
    total = calculate_cart_total()
    remaining = budget - total

    st.title("🎉 장보기 미션 결과")
    st.subheader(f"미션: {mission_name}")

    result_column1, result_column2, result_column3 = st.columns(3)

    result_column1.metric(
        "처음 예산",
        f"{budget:,}원",
    )

    result_column2.metric(
        "사용한 금액",
        f"{total:,}원",
    )

    result_column3.metric(
        "남은 돈",
        f"{remaining:,}원",
    )

    st.divider()
    st.header("🧾 구매한 물건")

    for item in st.session_state.cart.values():
        item_total = item["가격"] * item["수량"]

        image_column, information_column = st.columns(
            [1, 4]
        )

        with image_column:
            try:
                st.image(
                    item["이미지 url"],
                    use_container_width=True,
                )
            except Exception:
                st.image(
                    make_placeholder_image(),
                    use_container_width=True,
                )

        with information_column:
            st.subheader(item["품명"])
            st.write(f"한 개 가격: **{item['가격']:,}원**")
            st.write(f"구매 수량: **{item['수량']}개**")
            st.write(f"상품 합계: **{item_total:,}원**")

        st.divider()

    st.header("✏️ 구매 이유를 적어 보세요")

    purchase_reason = st.text_area(
        "왜 이 물건들을 골랐나요?",
        value=st.session_state.purchase_reason,
        placeholder=(
            "예: 카레를 만들 때 꼭 필요한 재료라고 생각해서 "
            "골랐습니다."
        ),
        height=150,
        max_chars=300,
    )

    st.session_state.purchase_reason = purchase_reason

    reason_completed = bool(purchase_reason.strip())

    if not reason_completed:
        st.info(
            "구매 이유를 작성하면 결과를 그림 파일로 저장할 수 있습니다."
        )
    else:
        result_svg = create_result_svg()

        safe_mission_name = (
            mission_name.replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

        st.download_button(
            label="🖼️ 그림으로 저장",
            data=result_svg,
            file_name=f"장보기_미션_{safe_mission_name}.svg",
            mime="image/svg+xml",
            use_container_width=True,
        )

        st.caption(
            "SVG 그림 파일은 글자와 상품 이미지가 확대되어도 "
            "선명하게 저장됩니다."
        )

    st.write("")

    button_column1, button_column2 = st.columns(2)

    with button_column1:
        if st.button(
            "🛒 쇼핑 화면으로 돌아가기",
            use_container_width=True,
        ):
            st.session_state.page = "shopping"
            st.rerun()

    with button_column2:
        if st.button(
            "🔄 새로운 미션 시작하기",
            use_container_width=True,
            type="primary",
        ):
            reset_app()
            st.rerun()


# --------------------------------------------------
# 페이지 실행
# --------------------------------------------------
if st.session_state.page == "start":
    show_start_page()

elif st.session_state.page == "shopping":
    show_shopping_page()

elif st.session_state.page == "result":
    show_result_page()

else:
    reset_app()
    st.rerun()
