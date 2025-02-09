import os
import configparser
from PIL import Image, ImageDraw, ImageFont
import textwrap
import argparse

def rgba_from_config(config_str):
    """Convert config RGBA string to tuple."""
    return tuple(map(int, config_str.split(',')))

def render_arabic_text_to_image(text, output_path, config, highlight_line=None):
    """
    Renders Arabic text to an image using settings from the given config.
    
    Args:
        text (str): Arabic text to render.
        output_path (str): Path to save the output PNG image.
        config (configparser.ConfigParser): Configuration object with an 'image' section.
        highlight_line (int, optional): 1-based index of the line to highlight.
    
    Returns:
        bool: True if the image was generated and saved successfully, False otherwise.
    """
    try:
        # Get config values with fallbacks
        image_section = config['image']
        
        font_family = image_section.get('FONT_FILE', 'Amiri')
        font_size = image_section.getint('FONT_SIZE', 48)
        image_width = image_section.getint('IMAGE_WIDTH', 1240)
        wrap_width = image_section.getint('WRAP_WIDTH', 170)
        vertical_padding = image_section.getint('VERTICAL_PADDING', 20)
        
        # Parse color values
        bg_color = rgba_from_config(image_section.get('BG_COLOR', '0,0,0,0'))
        text_color = rgba_from_config(image_section.get('TEXT_COLOR', '255,255,255,255'))
        highlight_color = rgba_from_config(image_section.get('HIGHLIGHT_COLOR', '255,0,0,255'))

        # Load font
        font = ImageFont.truetype(font_family, font_size)
        
        # Original text processing
        original_lines = text.split("\n")
        lines_with_bullets = [f"•{line}" for line in original_lines]

        wrapped_lines = []
        line_mapping = []
        highlighted_lines = []

        for i, line in enumerate(lines_with_bullets):
            is_highlighted = (highlight_line is not None) and (highlight_line == (i + 1))
            wrapped = textwrap.wrap(line, width=wrap_width)
            wrapped_lines.extend(wrapped)
            line_mapping.extend([i] * len(wrapped))
            highlighted_lines.extend([is_highlighted] * len(wrapped))

        # Calculate dimensions
        dummy_img = Image.new("RGBA", (image_width, 100), bg_color)
        draw = ImageDraw.Draw(dummy_img)
        _, _, _, text_height = draw.textbbox((0, 0), "A", font=font)
        line_height = text_height + 24
        total_text_height = line_height * len(wrapped_lines) + 2 * vertical_padding

        # Create image
        image = Image.new("RGBA", (image_width, total_text_height), bg_color)
        draw = ImageDraw.Draw(image)
        y = vertical_padding

        for i, line in enumerate(wrapped_lines):
            text_bbox = draw.textbbox((0, 0), line, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            x = image_width - text_width - 20  # Right-aligned

            color = highlight_color if highlighted_lines[i] else text_color
            draw.text((x, y), line, font=font, fill=color, direction="rtl")
            y += line_height

        image.save(output_path, "PNG")
        return True

    except Exception as e:
        print(f"Image generation error: {str(e)}")
        return False

def rgba_color(s):
    """
    Argument converter for RGBA strings.
    
    Ensures that the input is in the format "R,G,B,A" where each component is an integer.
    Returns the original string if valid.
    """
    parts = s.split(',')
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("Color must be in the format R,G,B,A")
    try:
        [int(x) for x in parts]
    except ValueError:
        raise argparse.ArgumentTypeError("Each color value must be an integer")
    return s

def build_config_from_args(args):
    """
    Build a configuration object (with an 'image' section) using command-line arguments.
    """
    config = configparser.ConfigParser()
    config['image'] = {
        'FONT_FILE': args.font_family,
        'FONT_SIZE': str(args.font_size),
        'IMAGE_WIDTH': str(args.image_width),
        'WRAP_WIDTH': str(args.wrap_width),
        'VERTICAL_PADDING': str(args.vertical_padding),
        'BG_COLOR': args.bg_color,
        'TEXT_COLOR': args.text_color,
        'HIGHLIGHT_COLOR': args.highlight_color,
    }
    return config

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Render Arabic text to image with configurable parameters.'
    )
    parser.add_argument('text', help='Arabic text to render')
    parser.add_argument('output_image_path', help='Output image path')
    parser.add_argument('highlight_line', nargs='?', type=int, default=None,
                        help='Line number to highlight (1-based index)')

    # Configurable parameters with environment variable defaults
    parser.add_argument('--image-width', type=int,
                        default=int(os.environ.get('PYTHON_IMAGE_WIDTH', 1240)),
                        help='Image width in pixels (default: 1240)')
    parser.add_argument('--wrap-width', type=int,
                        default=int(os.environ.get('PYTHON_IMAGE_WRAP_WIDTH', 170)),
                        help='Characters per line before wrapping (default: 170)')
    parser.add_argument('--font-size', type=int,
                        default=int(os.environ.get('PYTHON_IMAGE_FONT_SIZE', 48)),
                        help='Font size in points (default: 48)')
    parser.add_argument('--font-family', type=str,
                        default=os.environ.get('PYTHON_IMAGE_FONT', 'Amiri'),
                        help='Font family')
    parser.add_argument('--bg-color', type=rgba_color,
                        default=os.environ.get('PYTHON_IMAGE_BG_COLOR', '0,0,0,0'),
                        help='Background color as RGBA (default: 0,0,0,0)')
    parser.add_argument('--text-color', type=rgba_color,
                        default=os.environ.get('PYTHON_IMAGE_TEXT_COLOR', '255,255,255,255'),
                        help='Text color as RGBA (default: 255,255,255,255)')
    parser.add_argument('--highlight-color', type=rgba_color,
                        default=os.environ.get('PYTHON_IMAGE_HIGHLIGHT_COLOR', '255,0,0,255'),
                        help='Highlight color as RGBA (default: 255,0,0,255)')
    parser.add_argument('--vertical-padding', type=int,
                        default=int(os.environ.get('PYTHON_IMAGE_VERTICAL_PADDING', 20)),
                        help='Vertical padding in pixels (default: 20)')

    args = parser.parse_args()

    # Build a configuration object from the command-line arguments
    config = build_config_from_args(args)

    # Call the rendering function with the configuration object
    success = render_arabic_text_to_image(
        text=args.text,
        output_path=args.output_image_path,
        config=config,
        highlight_line=args.highlight_line
    )

    if success:
        print(f"Image saved to {args.output_image_path}")
    else:
        print("Failed to generate the image.")
