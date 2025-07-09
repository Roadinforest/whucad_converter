# C:\CATIA_Converter\convert_h5_to_catpart.py
import win32com.client
import h5py
import argparse
import os
import sys

# --- 关键：将当前目录添加到 Python 路径 ---
# 这能确保脚本可以找到我们复制过来的 whucad_lib 包
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- 从 whucad_lib 中导入必要的模块 ---
from whucad_lib.cadlib.CAD_Class import Macro_Seq
# create_CAD_CATIA 函数在 CAD_utils.py 中
from whucad_lib.cadlib.Catia_utils import create_CAD_CATIA


def convert_h5(input_h5_path, output_dir):
    """
    将单个 H5 文件转换为 .CATPart 文件。
    """
    # 1. 验证输入文件是否存在
    if not os.path.exists(input_h5_path):
        print(f"[ERROR] Input H5 file not found: {input_h5_path}")
        return

    print(f"[INFO] Processing file: {os.path.basename(input_h5_path)}")

    # 准备变量，以便在 finally 块中使用
    catia = None
    doc = None

    try:
        # 2. 读取 H5 文件中的向量数据
        with h5py.File(input_h5_path, 'r') as f:
            if 'vec' in f:
                macro_vec = f['vec'][:]
            elif 'out_vec' in f:
                macro_vec = f['out_vec'][:]
            else:
                raise KeyError("Could not find 'vec' or 'out_vec' dataset in H5 file.")

        print("[INFO] Vector data loaded from H5 file.")

        # 3. 将向量转换为 CAD 序列对象
        # is_numerical=True 表示向量中的参数是量化后的整数
        # n=256 是量化的范围，这与 WHUCAD 的设置匹配
        cad_seq = Macro_Seq.from_vector(macro_vec, is_numerical=True, n=256)
        print("[INFO] CAD sequence object created from vector.")

        # 4. 连接到 CATIA 应用
        print("[INFO] Connecting to CATIA application...")
        catia = win32com.client.Dispatch('catia.application')
        # 在转换期间让 CATIA 可见，方便观察过程
        catia.visible = True

        # 5. 创建新的 Part 文档
        doc = catia.documents.add('Part')
        part = doc.part
        print("[INFO] New CATPart document created.")

        # 6. 调用核心函数，在 CATIA 中构建几何体
        print("[INFO] Building geometry in CATIA... This may take a moment.")
        create_CAD_CATIA(cad_seq, catia, doc, part)
        print("[INFO] Geometry construction completed.")

        # 7. 保存为 .CATPart 文件
        base_name = os.path.splitext(os.path.basename(input_h5_path))[0]
        output_catpart_path = os.path.abspath(os.path.join(output_dir, f"{base_name}.CATPart"))

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        print(f"[INFO] Saving to: {output_catpart_path}")
        doc.SaveAs(output_catpart_path)

        print("\n" + "=" * 50)
        print(f"✅ Success! File converted and saved.")
        print("=" * 50)

    except Exception as e:
        import traceback
        print("\n" + "!" * 50)
        print(f"[FATAL ERROR] An error occurred during conversion.")
        print(f"   Error Type: {type(e).__name__}")
        print(f"   Message: {e}")
        print("--- Full Traceback ---")
        traceback.print_exc()
        print("!" * 50)
    finally:
        # 8. 清理：无论成功与否，都关闭创建的 CATIA 文档
        if doc:
            try:
                # 不保存任何未保存的更改并关闭
                doc.close()
                print("[INFO] CATIA document closed.")
            except Exception as close_e:
                print(f"[WARNING] Could not close CATIA document: {close_e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Convert a WHUCAD H5 file to a CATIA .CATPart file.")

    parser.add_argument('--input', type=str, required=True, help="Path to the input .h5 file.")
    parser.add_argument('--output_dir', type=str, default='./catia_parts',
                        help="Directory to save the output .CATPart file.")

    args = parser.parse_args()

    convert_h5(args.input, args.output_dir)