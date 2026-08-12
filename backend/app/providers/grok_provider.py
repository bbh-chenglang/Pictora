from time import perf_counter

from openai import APIError, APIStatusError, APITimeoutError
from openai.types.images_response import ImagesResponse

from app.observability import log_context
from app.providers.base import (
    ProviderRequestError,
    ProviderTimeoutError,
    image_data_url,
    normalize_image_results,
)
from app.providers.compatible_provider import CompatibleProvider
from app.providers.openai_provider import logger
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ReferenceImageInput,
    normalize_reference_images,
)


class GrokProvider(CompatibleProvider):
    provider_id = "grok"
    label = "Grok"

    async def generate_image(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImageInput | None = None,
    ) -> GenerateResponse:
        started_at = perf_counter()
        context = " ".join(f"{key}={value}" for key, value in log_context().items())
        logger.info(
            "image_generation step=provider_api_started provider=%s model=%s requested_count=%d %s",
            self.provider_id,
            request.model,
            request.count,
            context,
        )
        try:
            references = normalize_reference_images(reference_image)
            if len(references) > 3:
                raise ProviderRequestError(
                    response_content=b'{"error":{"message":"Grok supports at most 3 reference images"}}',
                    content_type="application/json",
                )
            native_parameters: dict[str, object] = {}
            if request.aspect_ratio is not None:
                native_parameters["aspect_ratio"] = request.aspect_ratio
            if request.resolution is not None:
                native_parameters["resolution"] = request.resolution.casefold()
            if (
                request.model.casefold() == "grok-imagine-image-2.0"
                and request.detail in {"low", "medium"}
            ):
                native_parameters["quality"] = request.detail
            if not references:
                response = await self.client.images.generate(
                    model=request.model,
                    prompt=request.prompt,
                    n=request.count,
                    response_format="b64_json",
                    extra_body=native_parameters,
                )
            else:
                image_inputs = [
                    {"url": image_data_url(image.data, image.content_type)}
                    for image in references
                ]
                body: dict[str, object] = {
                    "model": request.model,
                    "prompt": request.prompt,
                    "n": request.count,
                    "response_format": "b64_json",
                    **native_parameters,
                }
                if len(image_inputs) == 1:
                    body["image"] = image_inputs[0]
                else:
                    body["images"] = image_inputs
                response = await self.client.post(
                    "/images/edits",
                    body=body,
                    cast_to=ImagesResponse,
                )
        except APIStatusError as exc:
            error = ProviderRequestError(
                status_code=exc.status_code,
                response_content=exc.response.content,
                content_type=exc.response.headers.get("content-type"),
            )
            self._log_generation_failure(
                request,
                started_at,
                "api_status_error",
                status_code=error.status_code,
                upstream_message=error.message,
            )
            raise error from None
        except APITimeoutError:
            self._log_generation_failure(request, started_at, "timeout")
            raise ProviderTimeoutError() from None
        except APIError:
            self._log_generation_failure(request, started_at, "api_error")
            raise ProviderRequestError() from None

        images = normalize_image_results(response)
        logger.info(
            "image_generation step=provider_api_completed duration_ms=%d provider=%s model=%s image_count=%d %s",
            max(1, round((perf_counter() - started_at) * 1000)),
            self.provider_id,
            request.model,
            len(images),
            context,
        )
        return GenerateResponse(provider=self.provider_id, model=request.model, images=images)
