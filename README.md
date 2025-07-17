
# WHUCAD CATIA Worker

这是一个独立的 Python 项目，作为 WHUCAD-WebApp 的 Windows 端后台服务。它的核心功能是作为一个“工人”（Worker），接收由主后端（运行在 Linux 上）生成的 `.h5` CAD 向量文件，调用本地安装的 CATIA V5 将其转换为 `.CATPart` 文件，并将最终结果上传回主后端。

本项目解决了在 Linux 环境下无法直接调用 Windows 独占的 CATIA COM 接口的难题，实现了跨平台的分布式 CAD 文件生成。

## 功能特性

-   **自动化**: 自动轮询服务器以获取新任务，无需人工干预。
-   **CATIA 集成**: 通过 `pywin32` 库与本地 CATIA V5 应用进行深度交互，执行精确的几何构建操作。
-   **健壮性**: 包含错误处理和重试机制，能够应对网络中断和转换失败等情况。
-   **独立解耦**: 与主后端完全分离，可通过简单的 HTTP API 进行通信，易于部署和维护。
-   **包含手动转换工具**: 提供 `convert_h5_to_catpart.py` 脚本，用于本地调试和单个文件的快速转换。

## 项目结构

```
WHUCAD_converter/
├── worker.py                 # 主 Worker 程序，用于自动化处理任务队列
├── convert_h5_to_catpart.py  # 手动转换工具，用于单个 H5 文件的本地测试
├── whucad_lib/                 # 依赖的 WHUCAD 核心库
│   ├── __init__.py
│   └── cadlib/
│       ├── CAD_Class.py
│       ├── CAD_utils.py
│       └── macro.py
├── temp/                       # 自动创建的临时文件夹，用于存放下载和生成的中间文件
└── requirements.txt            # 项目依赖
```

-   **`worker.py`**: 部署时应该长期运行的主程序。
-   **`convert_h5_to_catpart.py`**: 用于开发和调试的辅助工具。
-   **`whucad_lib/`**: 从主项目 `pc2seq_whucad` 复制而来的核心 CAD 逻辑库，**必须**包含 `cadlib` 子目录。

## 环境配置

本项目需要在**安装了 CATIA V5 的 Windows 电脑**上运行。

1.  **安装 Python**:
    推荐使用 Anaconda 创建一个独立的 Python 3.8 或 3.9 环境，以获得最佳的 `pywin32` 兼容性。
    ```bash
    conda create -n whucad_converter python=3.9
    conda activate whucad_converter
    ```

2.  **安装依赖**:
    在项目根目录 `WHUCAD_converter/` 下有一个 `requirements.txt` 文件：
    ```txt
    pywin32
    h5py
    numpy
    requests
    ```
    然后通过 `pip` 安装：
    ```bash
    pip install -r requirements.txt
    ```

3.  **启动 CATIA V5**:
    在运行任何脚本**之前**，请确保 CATIA V5 应用程序已经手动打开并正在运行。（在一些环境下虽然不手动打开也可以正常运行，但是寻找时间+开启时间会十分长）

---

## 使用方法

本项目提供了两种运行模式：手动转换和自动化 Worker。

### 模式一：手动转换单个文件 (用于调试)

使用 `convert_h5_to_catpart.py` 脚本可以快速验证一个 `.h5` 文件的转换逻辑是否正确。

#### 主要逻辑

1.  接收一个输入 `.h5` 文件路径和一个输出目录作为命令行参数。
2.  读取 `.h5` 文件中的 `vec` 数据集。
3.  调用 `whucad_lib` 中的 `Macro_Seq.from_vector` 将向量转换为 CAD 对象序列。
4.  通过 `win32com` 连接到已打开的 CATIA 应用。
5.  创建一个新的 `.CATPart` 文档。
6.  调用 `create_CAD_CATIA` 函数，在 CATIA 中执行几何构建指令。
7.  将生成的零件保存到指定的输出目录。
8.  关闭在 CATIA 中创建的文档。

#### 如何使用

1.  将你的 `.h5` 文件（例如 `test.h5`）放置在项目目录下。
2.  打开 Anaconda Prompt 并激活环境 (`conda activate whucad_converter`)。
3.  `cd` 到 `WHUCAD_converter/` 目录。
4.  运行以下命令：
    ```bash
    python convert_h5_to_catpart.py --input test.h5
    ```
    转换成功后，你会在 `WHUCAD_converter/catia_parts/` 目录下找到 `test.CATPart` 文件。

### 模式二：自动化 Worker (用于生产/部署)

使用 `worker.py` 脚本来连接 Linux 主后端，实现全自动的分布式转换。

#### 主要逻辑

1.  进入一个无限循环，定期（默认每 5 秒）向主后端的 `/api/get_task/` 端点发送请求，询问是否有新任务，并在终端打印一个 `.`，表示正在轮询服务器。保持此窗口开启即可自动处理任务。按 `Ctrl+C` 可以停止 Worker。
2.  如果服务器返回一个任务，则：
    1. 根据任务中的 URL 下载对应的 `.h5` 文件到本地 `temp/` 文件夹。
    2. **执行与 `convert_h5_to_catpart.py` 完全相同的核心转换逻辑**，生成 `.CATPart` 文件。
    3. 生成的 `.CATPart` 文件通过 POST 请求上传回主后端的 `/api/task_update/` 端点，并更新任务状态为 `success`。
    4. 如果过程中任何一步失败，则向 `/api/task_update/` 发送状态为 `error` 的消息，并附上详细错误信息。
    5. 清理本地 `temp/` 文件夹中的临时文件。
3.  如果服务器没有返回任务，则等待下一个轮询周期。

#### 如何配置和使用

1.  **打开 `worker.py` 文件**。
2.  找到文件顶部的**配置部分**，并进行修改：

    ```python
    # worker.py
    
    # --- 配置 ---
    # !! 重要：这里的 IP 地址必须是你 Linux 主机的局域网 IP !!
    SERVER_URL = "http://<你的Linux主机IP>:8000" 
    
    # !! 重要：这个密钥必须与 Linux 后端 settings.py 中的 API_KEY 完全一致 !!
    API_KEY = "your_super_secret_key_12345"
    
    # 轮询间隔（秒），可以根据需要调整
    POLL_INTERVAL = 5
    # --- 配置结束 ---
    ```

3.  **运行 Worker**:
    *   确保 CATIA V5 已打开。
    *   在 Anaconda Prompt 中激活环境并 `cd` 到项目目录。
    *   运行以下命令：
        ```bash
        python worker.py
        ```
    *   终端会显示 `--- CATIA Worker Started ---`，并开始轮询服务器。
    *   你可以将这个终端窗口最小化，让它在后台一直运行。要停止 Worker，只需在该终端中按 `Ctrl+C`。

这个 Worker 会持续工作，只要 Linux 主后端有新的 H5 文件生成，它就会自动处理，实现完整的自动化流程。
