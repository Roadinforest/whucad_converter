import win32com.client
import h5py
import os
import sys
import time
import requests
import traceback

# Windows上用于连接Linux后端的重要逻辑文件
# --- 关键：将当前目录和 whucad_lib 目录添加到 Python 路径 ---
# 这能确保脚本可以找到我们复制过来的 whucad_lib 包
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(CURRENT_DIR)

# --- 从 whucad_lib 中导入必要的模块 ---
from whucad_lib.cadlib.CAD_Class import Macro_Seq
from whucad_lib.cadlib.Catia_utils import create_CAD_CATIA

# --- 配置 ---
# !! 重要：这里的 IP 地址必须是你 Linux 主机的局域网 IP !!
SERVER_URL = "http://192.168.169.37:8000"  # <--- 修改为你的 Linux 主机 IP
API_KEY = "your_super_secret_key_12345"  # <--- 与Linux后端Django 中settings.py 中的一致
POLL_INTERVAL = 5  # 每 5 秒轮询一次
# --- 配置结束 ---

def process_task(task):
    """
    处理从服务器接收到的单个转换任务。
    """
    h5_relative_url = task['h5_url']  # e.g., /media/results/task.h5
    task_id = task['task_id']

    print(f"\n--- [{task_id}] New task received. H5 URL: {h5_relative_url} ---")

    # 定义本地临时文件的路径
    os.makedirs("temp", exist_ok=True)
    local_h5_path = os.path.join("temp", f"{task_id}.h5")
    local_catpart_path = os.path.abspath(os.path.join("temp", f"{task_id}.CATPart"))

    # --- 1. 下载 H5 文件 ---
    try:
        print(f"[{task_id}] Step 1/4: Downloading H5 file...")
        h5_full_url = f"{SERVER_URL}{h5_relative_url}"
        response = requests.get(h5_full_url)
        response.raise_for_status()  # 如果下载失败 (如 404)，则抛出异常

        with open(local_h5_path, 'wb') as f:
            f.write(response.content)
        print(f"[{task_id}] H5 file downloaded to '{local_h5_path}'.")

    except Exception as e:
        print(f"[{task_id}] ERROR: Failed to download H5 file: {e}")
        # 下载失败，通知服务器任务出错
        requests.post(f"{SERVER_URL}/api/task_update/",
                      json={'task_id': task_id, 'status': 'error', 'message': f"Worker failed to download H5: {e}",
                            'api_key': API_KEY})
        return

    # --- 2. 核心 CATIA 转换逻辑 ---
    catia = None
    doc = None
    try:
        print(f"[{task_id}] Step 2/4: Starting CATIA conversion...")

        with h5py.File(local_h5_path, 'r') as f:
            macro_vec = f['vec'][:] if 'vec' in f else f['out_vec'][:]

        cad_seq = Macro_Seq.from_vector(macro_vec, is_numerical=True, n=256)

        catia = win32com.client.Dispatch('catia.application')
        catia.visible = True  # 调试时设为 True，部署时可设为 False

        doc = catia.documents.add('Part')
        part = doc.part

        create_CAD_CATIA(cad_seq, catia, doc, part)

        doc.SaveAs(local_catpart_path)
        print(f"[{task_id}] CATPart file successfully saved locally to: {local_catpart_path}")

    except Exception as e:
        error_msg = f"CATIA conversion failed: {e}\n{traceback.format_exc()}"
        print(f"[{task_id}] ERROR: {error_msg}")
        # 转换失败，通知服务器任务出错
        requests.post(f"{SERVER_URL}/api/task_update/",
                      json={'task_id': task_id, 'status': 'error', 'message': error_msg, 'api_key': API_KEY})
        return
    finally:
        if doc:
            try:
                doc.close()
            except Exception:
                pass  # 忽略关闭文档时可能出现的错误

    # --- 3. 上传转换后的 .CATPart 文件 ---
    try:
        print(f"[{task_id}] Step 3/4: Uploading result file...")
        with open(local_catpart_path, 'rb') as f:
            files = {'file': (os.path.basename(local_catpart_path), f)}
            # 在 data 中发送任务的最终状态
            data = {'task_id': task_id, 'status': 'success', 'api_key': API_KEY}
            response = requests.post(f"{SERVER_URL}/api/task_update/", files=files, data=data)
            response.raise_for_status()
        print(f"[{task_id}] Step 4/4: Task completed and result uploaded.")

    except Exception as e:
        error_msg = f"Failed to upload result file: {e}"
        print(f"[{task_id}] ERROR: {error_msg}")
        # 上传失败，通知服务器任务出错
        requests.post(f"{SERVER_URL}/api/task_update/",
                      json={'task_id': task_id, 'status': 'error', 'message': error_msg, 'api_key': API_KEY})
    finally:
        # --- 4. 清理本地临时文件 ---
        if os.path.exists(local_h5_path): os.remove(local_h5_path)
        if os.path.exists(local_catpart_path): os.remove(local_catpart_path)


def main():
    """
    主循环，不断向服务器轮询新任务。
    """
    print("--- CATIA Worker Started ---")
    print(f"Polling server at {SERVER_URL} every {POLL_INTERVAL} seconds.")
    print("Press Ctrl+C to stop.")

    while True:
        try:
            get_task_url = f"{SERVER_URL}/api/get_task/"
            response = requests.get(get_task_url, params={'api_key': API_KEY}, timeout=10)

            if response.status_code == 200:
                task_data = response.json()
                if task_data and task_data.get('task_id'):
                    process_task(task_data)
                else:
                    print(".", end="", flush=True)
            elif response.status_code == 204:
                print(".", end="", flush=True)
            else:
                print(f"\n[WARNING] Error polling for tasks: {response.status_code} - {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"\n[ERROR] Connection to server failed: {e}")
        except Exception as e:
            print(f"\n[ERROR] An unexpected error occurred in the main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()