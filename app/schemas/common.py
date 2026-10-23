"""
统一响应的通用格式
"""

def ajax_success(data=None)->dict:
    """返回成功响应格式"""
    return {"code": 200, "msg": "success", "data": data}

def ajax_error(data=None)->dict:
    """返回错误响应格式"""
    return {"code": 400, "msg": "error", "data": data}
