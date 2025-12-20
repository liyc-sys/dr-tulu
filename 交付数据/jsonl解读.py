import json
import os

def analyze_jsonl_structure(file_path):
    """
    读取 JSONL 文件的第一行，分析其结构并生成访问代码建议。
    """
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if not first_line:
                print("错误: 文件是空的。")
                return
            
            # 尝试解析第一行
            sample_data = json.loads(first_line)
            
            print("="*60)
            print(f"文件: {file_path}")
            print("解析成功！以下是该 JSONL 每一行数据的结构分析：")
            print("="*60)
            
            # 递归分析并打印访问路径
            print_structure(sample_data, root_name="item")
            
            print("\n" + "="*60)
            print("推荐的读取代码模板 (你可以直接复制使用):")
            print("="*60)
            generate_template_code(file_path)

    except json.JSONDecodeError:
        print("错误: 第一行不是有效的 JSON 格式。请检查文件是否为 JSONL。")
    except Exception as e:
        print(f"发生未知错误: {e}")

def print_structure(data, root_name="item", indent=0):
    """
    递归打印数据结构和访问路径
    """
    prefix = "  " * indent
    
    if isinstance(data, dict):
        print(f"{prefix}# [字典 Dict] - 包含 {len(data)} 个键")
        for key, value in data.items():
            # 构建访问路径字符串
            current_path = f"{root_name}['{key}']"
            # 检查值的类型
            if isinstance(value, (dict, list)):
                print(f"{prefix}- 键: '{key}'")
                print_structure(value, current_path, indent + 1)
            else:
                type_name = type(value).__name__
                print(f"{prefix}- {current_path:<40} # 类型: {type_name}, 示例: {repr(value)}")
                
    elif isinstance(data, list):
        print(f"{prefix}# [列表 List] - 长度: {len(data)}")
        if len(data) > 0:
            print(f"{prefix}# 下面展示列表中的第一个元素结构:")
            current_path = f"{root_name}[0]" 
            print_structure(data[0], current_path, indent + 1)
        else:
            print(f"{prefix}# (空列表)")
    else:
        # 基本数据类型
        type_name = type(data).__name__
        print(f"{prefix}{root_name} # 类型: {type_name}, 示例: {data}")

def generate_template_code(file_path):
    """
    生成一段可以直接使用的 Python 代码
    """
    code = f"""
import json

file_path = '{file_path}'

# 打开文件并逐行读取
with open(file_path, 'r', encoding='utf-8') as f:
    for line_number, line in enumerate(f):
        try:
            line = line.strip()
            if not line: continue # 跳过空行
            
            # item 就是每一行的 json 对象
            item = json.loads(line)
            
            # TODO: 在这里编写你的逻辑
            # 例如 (基于刚才的分析):
            # print(item.get('你的某个键'))
            
        except json.JSONDecodeError:
            print(f"第 {{line_number + 1}} 行解析失败")
"""
    print(code)

# ==========================================
# 为了演示，我们先创建一个假的 JSONL 文件
# ==========================================
def create_dummy_jsonl():
    dummy_data = {
        "id": 1001,
        "user_info": {
            "name": "张三",
            "is_active": True,
            "roles": ["admin", "editor"]
        },
        "content": "这是一段测试文本。",
        "metrics": None
    }
    filename = "test_data.jsonl"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(json.dumps(dummy_data, ensure_ascii=False) + "\n")
        # 写入第二行以模拟真实文件
        dummy_data['id'] = 1002
        f.write(json.dumps(dummy_data, ensure_ascii=False) + "\n")
    return filename

if __name__ == "__main__":
    # 1. 生成测试文件 (你可以把这行换成你自己的文件路径)
    # target_file = create_dummy_jsonl()
    target_file = "/Users/liyc/Desktop/dr-tulu/交付数据/pubmed_trajectory_20251218_060613_no_rubrics_incremental_fixed.jsonl"
    
    # 2. 分析文件
    analyze_jsonl_structure(target_file)