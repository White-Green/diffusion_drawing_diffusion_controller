import asyncio
import json
import os
import random
from urllib import request


async def async_urlopen(req: request.Request):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, request.urlopen, req)


def replace_random_seed(obj):
    if isinstance(obj, list):
        return [replace_random_seed(element) for element in obj]
    elif isinstance(obj, dict):
        return {key: replace_random_seed(value) for key, value in obj.items()}

    if obj == "${RANDOM_SEED}":
        return random.randint(0, 2 ** 32)
    else:
        return obj


def scribble_to_line_workflow():
    with open(os.path.join(os.path.dirname(__file__), "scribble_to_line_api.json"), "r") as f:
        scribble_to_line_obj = json.load(f)
    return replace_random_seed(scribble_to_line_obj)


def detail_colored_workflow():
    with open(os.path.join(os.path.dirname(__file__), "detail_colored_api.json"), "r") as f:
        detail_colored_obj = json.load(f)
    return replace_random_seed(detail_colored_obj)


class ComfyUIController:
    def __init__(self, host: str):
        self.host = host

    async def upload_image(self, image_path: str, file_name: str):
        with open(image_path, "rb") as f:
            file_data = f.read()

        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = ((
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"overwrite\"\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"\r\n"
                    f"true\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Disposition: form-data; name=\"image\"; filename=\"{file_name}\"\r\n"
                    f"Content-Type: image/png\r\n"
                    f"\r\n"
                ).encode('utf-8')
                + file_data
                + (
                    f"\r\n"
                    f"--{boundary}--\r\n"
                ).encode('utf-8'))
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        upload_request = request.Request(f"{self.host}/upload/image", data=body, headers=headers, method="POST")

        await async_urlopen(upload_request)

    async def execute_prompt(self, prompt: any) -> list[(str, bytes)]:
        if type(prompt) is str:
            prompt = json.loads(prompt)

        prompt = {"prompt": prompt}
        req = request.Request(f"{self.host}/prompt", data=json.dumps(prompt).encode('utf-8'),
                              headers={"Content-Type": "application/json"}, method="POST")
        resp = await async_urlopen(req)
        response_object = json.loads(resp.read())
        prompt_id = response_object["prompt_id"]

        history_object = {}
        while prompt_id not in history_object:
            history_request = request.Request(f"{self.host}/history?max_items=64")
            history_response = await async_urlopen(history_request)
            history_object = json.loads(history_response.read())
            await asyncio.sleep(0.2)

        history_object = history_object[prompt_id]
        output_object = list(history_object["outputs"].items())
        result_images = []
        for output_object in output_object:
            output_image = output_object[1]["images"]
            assert len(output_image) == 1
            output_image = output_image[0]
            output_image_request = request.Request(
                f"{self.host}/view?filename={output_image['filename']}&type={output_image['type']}"
            )
            output_image_response = await async_urlopen(output_image_request)
            result_images.append((output_object[0], output_image_response.read()))
        return result_images


class DiffusionController:
    def __init__(self):
        self.comfy = ComfyUIController("http://localhost:8818")
        pass

    async def scribble_to_line(self, scribble_image_path: str, lineart_image_path: str, output_image_path: str):
        """
        入力されたScribble画像と描き途中の線画画像から全体の線画画像を生成して、
        指定された出力パスに保存する

        引数:
            scribble_image_path (str): 入力用のScribble画像(白背景)のパス。
            lineart_image_path (str): 現在描き途中のlineart画像(透過)のパス。
            output_image_path (str): 生成された線画画像を保存するパス。
        """
        scribble_file_name = "diffusion_drawing_temporary_scribble.png"
        lineart_file_path = "diffusion_drawing_temporary_lineart.png"
        await asyncio.gather(
            self.comfy.upload_image(scribble_image_path, scribble_file_name),
            self.comfy.upload_image(lineart_image_path, lineart_file_path)
        )
        result_images = await self.comfy.execute_prompt(scribble_to_line_workflow())
        assert len(result_images) == 1
        with open(output_image_path, "wb") as f:
            f.write(result_images[0][1])

    async def detail_colored(self,
                             image_path: str,
                             basecolor_image_path: str,
                             lineart_path: str,
                             basecolor_path: str,
                             shadow_path: str,
                             light_path: str,
                             output_shadow_path: str,
                             output_light_path: str):
        """
        入力されたScribble画像と描き途中の線画画像から全体の線画画像を生成して、
        指定された出力パスに保存する

        引数:
            image_path (str): 現在描き途中の画像(白背景)のパス
            basecolor_image_path (str): 現在描き途中の画像から影とハイライトを除いた画像(白背景)のパス
            lineart_path (str): 線画のみの画像(透過)のパス
            basecolor_path (str): 下塗りのみの画像(透過)のパス
            shadow_path (str): 影のみの画像(透過)のパス
            light_path (str): ハイライトのみの画像(透過)のパス
            output_shadow_path (str): 生成された影画像を保存するパス
            output_light_path (str): 生成されたハイライト画像を保存するパス
        """
        image_file_name = "diffusion_drawing_temporary_image.png"
        basecolor_image_file_name = "diffusion_drawing_temporary_basecolor_image.png"
        lineart_file_name = "diffusion_drawing_temporary_lineart.png"
        basecolor_file_name = "diffusion_drawing_temporary_basecolor.png"
        shadow_file_name = "diffusion_drawing_temporary_shadow.png"
        light_file_name = "diffusion_drawing_temporary_light.png"
        await asyncio.gather(
            self.comfy.upload_image(image_path, image_file_name),
            self.comfy.upload_image(basecolor_image_path, basecolor_image_file_name),
            self.comfy.upload_image(lineart_path, lineart_file_name),
            self.comfy.upload_image(basecolor_path, basecolor_file_name),
            self.comfy.upload_image(shadow_path, shadow_file_name),
            self.comfy.upload_image(light_path, light_file_name),
        )
        result_images = await self.comfy.execute_prompt(detail_colored_workflow())
        assert len(result_images) == 2
        result_images = dict(result_images)
        with open(output_shadow_path, "wb") as f:
            f.write(result_images["65"])
        with open(output_light_path, "wb") as f:
            f.write(result_images["67"])
