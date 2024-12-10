from typing import Tuple

MIN_GENERATION_PIXELS = 512 * 320  # 163,840 pixels minimum

def calculate_generation_dimensions(target_width: int, target_height: int) -> Tuple[int, int]:
    """
    Calculate dimensions by incrementing either width or height in steps of 8
    until minimum pixel count is reached. Choose which dimension to increment
    based on current vs target aspect ratio.
    """
    target_ratio = target_width / target_height
    width = 8
    height = 8

    while width * height < MIN_GENERATION_PIXELS:
        current_ratio = width / height

        # If current ratio is smaller than target, increase width
        # If current ratio is larger than target, increase height
        if current_ratio < target_ratio:
            width += 8
        else:
            height += 8

    return width, height


if __name__ == "__main__":
    test_cases = [
        (16, 9),         # Standard widescreen
        (4, 3),          # Standard monitor
        (1920, 1080),    # Full HD
        (7680, 4320),    # 8K
        (1, 1),          # Square
        (1000, 7),       # Extreme ratio
        (3, 1000),       # Another extreme ratio
        (15360, 8640),   # 16K
        (1, 2),          # Simple ratio
        (2560, 1440),    # 2K
        # Edge cases
        (8, 8),          # Already divisible by 8
        (7, 7),          # Prime numbers
        (23, 37),        # Prime numbers
        (99, 151),       # More odd numbers
        (1001, 1001),    # Large odd numbers
    ]

    for w, h in test_cases:
        output_width, output_height = calculate_generation_dimensions(w, h)
        aspect_ratio_original = w / h
        aspect_ratio_final = output_width / output_height
        ratio_diff_percent = abs(aspect_ratio_final - aspect_ratio_original) / aspect_ratio_original * 100

        print(f"\nInput: {w}x{h}")
        print("Overshoot:", (output_width * output_height) / MIN_GENERATION_PIXELS)
        print(f"Output: {output_width}x{output_height}")
        print(f"Pixels: {output_width * output_height:,} (min: {MIN_GENERATION_PIXELS:,})")
        print(f"Original ratio: {w}/{h} = {aspect_ratio_original:.4f}")
        print(f"Final ratio: {output_width}/{output_height} = {aspect_ratio_final:.4f}")
        print(f"Ratio difference: {ratio_diff_percent:.2f}%")
        print(f"Width multiple of 8: {output_width % 8 == 0}")
        print(f"Height multiple of 8: {output_height % 8 == 0}")
        print("---")