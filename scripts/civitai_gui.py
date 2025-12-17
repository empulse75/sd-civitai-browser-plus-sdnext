import gradio as gr
from modules import script_callbacks, shared, paths
from modules.shared import opts, cmd_opts
import os
import json
import fnmatch
import re
import subprocess

# Local imports
import scripts.civitai_global as gl
from scripts.civitai_global import print
import scripts.civitai_download as _download
import scripts.civitai_file_manage as _file
import scripts.civitai_api as _api

def git_tag():
    try:
        git_cmd = os.environ.get('GIT', "git")
        return subprocess.check_output([git_cmd, "describe", "--tags"], shell=False, encoding='utf8').strip()
    except Exception:
        return None

# Version Detection
forge = False
ver_bool = True

try:
    import modules_forge
    forge = True
except ImportError:
    pass

if not forge:
    try:
        from packaging import version
        ver = git_tag()

        if not ver:
            try:
                from modules import launch_utils
                ver = launch_utils.git_tag()
            except Exception:
                ver_bool = False
        
        if ver:
            # Clean version string (e.g., v1.7.0-RC -> 1.7.0)
            ver_clean = ver.split('-')[0].lstrip('v')
            ver_bool = version.parse(ver_clean) >= version.parse("1.7")
    except ImportError:
        print("Python module 'packaging' issue. Assuming compatible version.")
        ver_bool = False

# Initialize Global State
gl.init()

def saveSettings(ust, ct, pt, st, bf, cj, td, ol, hi, sn, ss, ts):
    config_file = cmd_opts.ui_config_file
    
    settings_map = {
        "civitai_interface/Search type:/value": ust,
        "civitai_interface/Content type:/value": ct,
        "civitai_interface/Time period:/value": pt,
        "civitai_interface/Sort by:/value": st,
        "civitai_interface/Base model:/value": bf,
        "civitai_interface/Save info after download/value": cj,
        "civitai_interface/Divide cards by date/value": td,
        "civitai_interface/Liked models only/value": ol,
        "civitai_interface/Hide installed models/value": hi,
        "civitai_interface/NSFW content/value": sn,
        "civitai_interface/Tile size:/value": ss,
        "civitai_interface/Tile count:/value": ts
    }
    
    try:
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf8") as file:
                data = json.load(file)
        else:
            data = {}
            
        # Clean old keys
        data = {k: v for k, v in data.items() if "civitai_interface" not in k}
        
        # Update new keys
        data.update(settings_map)

        with open(config_file, 'w', encoding="utf-8") as file:
            json.dump(data, file, indent=4)
            print(f"Updated settings to: {config_file}")
            
    except Exception as e:
        print(f"Failed to save settings to {config_file}: {e}")

def all_visible(html_check):
    return gr.Button.update(visible="model-checkbox" in html_check)
        
def HTMLChange(input_val):
    return gr.HTML.update(value=input_val)

def show_multi_buttons(model_list_json, type_list_json, version_value):
    try:
        model_list = json.loads(model_list_json)
        type_list = json.loads(type_list_json)
    except (ValueError, TypeError):
        model_list = []
        type_list = []

    otherButtons = not bool(model_list)
    multi_file_subfolder = False
    default_subfolder = "Only available if the selected files are of the same model type"
    sub_folders = ["None"]
    
    is_installed = version_value and version_value.endswith('[Installed]')
    btn_dwn_visible = bool(version_value and not is_installed and not model_list)
    btn_del_visible = bool(is_installed and not model_list)
    
    dot_subfolders = getattr(opts, "dot_subfolders", True)
    multi_active = bool(model_list) and not (len(gl.download_queue) > 0)

    if type_list and all(x == type_list[0] for x in type_list):
        multi_file_subfolder = True
        model_folder = _api.contenttype_folder(type_list[0])
        default_subfolder = "None"
        try:
            folder_list = []
            for root, dirs, _ in os.walk(model_folder, followlinks=True):
                if dot_subfolders:
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for d in dirs:
                    # Skip hidden paths if configured
                    if dot_subfolders and any(part.startswith('.') for part in os.path.join(root, d).split(os.sep)):
                        continue
                        
                    rel_path = os.path.relpath(os.path.join(root, d), model_folder)
                    if rel_path:
                        folder_list.append(f'{os.sep}{rel_path}')
            
            # De-duplicate and sort
            unique_folders = sorted(list(set(folder_list)), key=lambda x: (x.lower(), x))
            sub_folders.extend(unique_folders)
            
        except Exception:
            sub_folders = ["None"]
    
    return (
        gr.Button.update(visible=multi_active, interactive=multi_active), # Download Multi
        gr.Button.update(visible=btn_dwn_visible if not multi_active else False), # Download Single
        gr.Button.update(visible=btn_del_visible), # Delete
        gr.Button.update(visible=otherButtons), # Save Info
        gr.Button.update(visible=otherButtons), # Save Images
        gr.Dropdown.update(visible=multi_active, interactive=multi_file_subfolder, choices=sub_folders, value=default_subfolder) # Subfolder
    )

def txt2img_output(image_url):
    if not image_url: 
        return gr.Textbox.update(value="")
        
    clean_url = image_url[4:] if image_url.startswith("http") else image_url
    geninfo = _api.fetch_and_process_image(clean_url)
    
    if geninfo:
        nr = _download.random_number()
        return gr.Textbox.update(value=f"{nr}{geninfo}")
    return gr.Textbox.update()

def get_base_models():
    """
    Returns a static list of base models.
    Refactored to remove brittle API dependency that caused startup hangs.
    """
    return [
        "AuraFlow", "Chroma", "CogVideoX", "Flux.1 D", "Flux.1 Krea", "Flux.1 Kontext", "Flux.1 S", "Flux.2 D", 
        "HiDream", "Hunyuan 1", "Hunyuan Video", "Illustrious", "Imagen4", "Kolors", "LTXV", "Lumina", 
        "Mochi", "Nano Banana", "NoobAI", "ODOR", "OpenAI", 
        "PixArt E", "PixArt a", "Playground v2", "Pony", "Pony V7", "Qwen", 
        "SD 1.4", "SD 1.5", "SD 1.5 Hyper", "SD 1.5 LCM", "SD 2.0", "SD 2.0 768", "SD 2.1", "SD 2.1 768", "SD 2.1 Unclip", 
        "SD 3", "SD 3.5", "SD 3.5 Large", "SD 3.5 Large Turbo", "SD 3.5 Medium", 
        "SDXL 0.9", "SDXL 1.0", "SDXL 1.0 LCM", "SDXL Distilled", "SDXL Hyper", "SDXL Lightning", "SDXL Turbo", 
        "SVD", "SVD XT", "Seedream", "Sora 2", "Stable Cascade", "Veo 3", "Wan Video", 
        "Other"
    ]

def on_ui_tabs():    
    page_header = getattr(opts, "page_header", False)
    lobe_directory = None
    
    for root, dirs, files in os.walk(paths.extensions_dir, followlinks=True):
        for dir_name in fnmatch.filter(dirs, '*lobe*'):
            lobe_directory = os.path.join(root, dir_name)
            break

    suffix = "L" if lobe_directory else ""
    component_id = f"toggles{suffix}"
    
    api_key = getattr(opts, "custom_api_key", "")
    show_only_liked = bool(api_key)
    toggle4_id = f"toggle4{suffix}_api" if api_key else f"toggle4{suffix}"
    
    header_id = f"header{suffix}" if page_header else "header_off"

    content_choices = _file.get_content_choices()
    scan_choices = _file.get_content_choices(scan_choices=True)
    
    with gr.Blocks() as civitai_interface:
        with gr.Tab(label="Browser", elem_id="browserTab"):
            with gr.Column(elem_id="filterAndSearchArea"):
                with gr.Column(elem_id=f"filterBox{suffix}"):
                    with gr.Row():
                        with gr.Column():
                            gr.HTML("<div class='filter-header'>Search Type</div>")
                            use_search_term = gr.Radio(label="Search type:", choices=["Model name", "User name", "Tag"], value="Model name", elem_id="searchType", show_label=False)
                    with gr.Row():
                        with gr.Column(scale=1, min_width=200):
                             gr.HTML("<div class='filter-header'>Time Period</div>")
                             period_type = gr.Radio(label='Time period:', choices=["All Time", "Year", "Month", "Week", "Day"], value="All Time", elem_id="chipGroup", show_label=False)
                        with gr.Column(scale=3):
                            gr.HTML("<div class='filter-header'>Model Types</div>")
                            content_type = gr.CheckboxGroup(label='Content type:', choices=content_choices, value=None, type="value", elem_id="chipGroup", show_label=False)
                            gr.HTML("<div class='filter-header'>Base Model Categories</div>")
                            base_filter = gr.CheckboxGroup(label='Base model:', choices=get_base_models(), value=None, type="value", elem_id="centerText", show_label=False)
                    with gr.Row():
                        with gr.Column():
                            gr.HTML("<div class='filter-header'>Sort By</div>")
                            sort_type = gr.Radio(label='Sort by:', choices=["Newest","Oldest","Most Downloaded","Highest Rated","Most Liked","Most Buzz","Most Discussed","Most Collected","Most Images"], value="Most Downloaded", elem_id="chipGroup", show_label=False)
                    with gr.Row(elem_id=component_id):
                        create_json = gr.Checkbox(label=f"Save info after download", value=True, elem_id=f"toggle1{suffix}", min_width=171)
                        show_nsfw = gr.Checkbox(label="NSFW content", value=False, elem_id=f"toggle2{suffix}", min_width=107)
                        toggle_date = gr.Checkbox(label="Divide cards by date", value=False, elem_id=f"toggle3{suffix}", min_width=142)
                        only_liked = gr.Checkbox(label="Liked models only", value=False, interactive=show_only_liked, elem_id=toggle4_id, min_width=163)
                        hide_installed = gr.Checkbox(label="Hide installed models", value=False, elem_id=f"toggle5{suffix}", min_width=170)
                    with gr.Row():
                        size_slider = gr.Slider(minimum=4, maximum=20, value=8, step=0.25, label='Tile size:')
                        tile_count_slider = gr.Slider(label="Tile count:", minimum=1, maximum=100, value=15, step=1)
                    with gr.Row(elem_id="save_set_box"):
                        save_settings = gr.Button(value="Save settings as default", elem_id="save_set_btn")
                with gr.Row(elem_id="searchRow"): 
                    search_term = gr.Textbox(label="", placeholder="Search CivitAI", elem_id="searchBox")
                    refresh = gr.Button(value="🔎", elem_id=f"refreshBtn{suffix}")
            
            with gr.Row(elem_id=header_id):
                with gr.Row(elem_id="pageBox"):
                    get_prev_page = gr.Button(value="Prev page", interactive=False, elem_id="pageBtn1")
                    page_slider = gr.Slider(label='Current page:', step=1, minimum=1, maximum=1, min_width=80, elem_id="pageSlider")
                    get_next_page = gr.Button(value="Next page", interactive=False, elem_id="pageBtn2")
                with gr.Row(elem_id="pageBoxMobile"):
                    pass 

            with gr.Row(elem_id="select_all_models_container"):
                select_all = gr.Button(value="Select All", elem_id="select_all_models", visible=False)
            with gr.Row():
                list_html = gr.HTML(value='<div style="font-size: 24px; text-align: center; margin: 50px;">Click the search icon to load models.<br>Use the filter icon to filter results.</div>')
            with gr.Row():
                download_progress = gr.HTML(value='<div style="min-height: 0px;"></div>', elem_id="DownloadProgress")
            with gr.Row():
                list_models = gr.Dropdown(label="Model:", choices=[], interactive=False, elem_id="quicksettings1", value=None)
                list_versions = gr.Dropdown(label="Version:", choices=[], interactive=False, elem_id="quicksettings0", value=None)
                file_list = gr.Dropdown(label="File:", choices=[], interactive=False, elem_id="file_list", value=None)
            with gr.Row():
                with gr.Column(scale=4):
                    install_path = gr.Textbox(label="Download folder:", interactive=False, max_lines=1)
                with gr.Column(scale=2):
                    sub_folder = gr.Dropdown(label="Sub folder:", choices=[], interactive=False, value=None)
            with gr.Row():
                with gr.Column(scale=4):
                    trained_tags = gr.Textbox(label='Trained tags (if any):', value=None, interactive=False, lines=1)
                with gr.Column(scale=2, elem_id="spanWidth"):
                    base_model = gr.Textbox(label='Base model: ', value=None, interactive=False, lines=1, elem_id="baseMdl")
                    model_filename = gr.Textbox(label="Model filename:", interactive=False, value=None)
            with gr.Row():
                save_info = gr.Button(value="Save model info", interactive=False)
                save_images = gr.Button(value="Save images", interactive=False)
                delete_model = gr.Button(value="Delete model", interactive=False, visible=False)
                download_model = gr.Button(value="Download model", interactive=False)
                subfolder_selected = gr.Dropdown(label="Sub folder for selected files:", choices=[], interactive=False, visible=False, value=None, allow_custom_value=True)
                download_selected = gr.Button(value="Download all selected", interactive=False, visible=False, elem_id="download_all_button")
            with gr.Row():
                cancel_all_model = gr.Button(value="Cancel all downloads", interactive=False, visible=False)
                cancel_model = gr.Button(value="Cancel current download", interactive=False, visible=False)
            with gr.Row():
                preview_html = gr.HTML(elem_id="civitai_preview_html")
            with gr.Row(elem_id="backToTopContainer"):
                back_to_top = gr.Button(value="↑", elem_id="backToTop")
        
        with gr.Tab("Update Models"):
            with gr.Row():
                selected_tags = gr.CheckboxGroup(elem_id="selected_tags", label="Selected content types:", choices=scan_choices)
            with gr.Row(elem_id="civitai_update_toggles"):
                overwrite_toggle = gr.Checkbox(elem_id="overwrite_toggle", label="Overwrite any existing files.", value=True, min_width=300)
                skip_hash_toggle = gr.Checkbox(elem_id="skip_hash_toggle", label="One-Time Hash Generation.", value=True, min_width=300)
                do_html_gen = gr.Checkbox(elem_id="do_html_gen", label="Save HTML file.", value=False, min_width=300)
            
            with gr.Row():
                save_all_tags = gr.Button(value="Update model info & tags", interactive=True)
                cancel_all_tags = gr.Button(value="Cancel", interactive=False, visible=False)
            with gr.Row():
                tag_progress = gr.HTML(value='<div style="min-height: 0px;"></div>')
            
            with gr.Row():
                update_preview = gr.Button(value="Update model preview", interactive=True)
                cancel_update_preview = gr.Button(value="Cancel", interactive=False, visible=False)
            with gr.Row():
                preview_progress = gr.HTML(value='<div style="min-height: 0px;"></div>')
            
            with gr.Row():
                ver_search = gr.Button(value="Scan for available updates", interactive=True)
                cancel_ver_search = gr.Button(value="Cancel", interactive=False, visible=False)
                load_to_browser = gr.Button(value="Load outdated models to browser", interactive=False, visible=False)
            with gr.Row():
                version_progress = gr.HTML(value='<div style="min-height: 0px;"></div>')
            
            with gr.Row():
                load_installed = gr.Button(value="Load all installed models", interactive=True)
                cancel_installed = gr.Button(value="Cancel", interactive=False, visible=False)
                load_to_browser_installed = gr.Button(value="Load installed models to browser", interactive=False, visible=False)
            with gr.Row():
                installed_progress = gr.HTML(value='<div style="min-height: 0px;"></div>')
            
            with gr.Row():
                organize_models = gr.Button(value="Organize model files", interactive=True, visible=False)
                cancel_organize = gr.Button(value="Cancel", interactive=False, visible=False)
            with gr.Row():
                organize_progress = gr.HTML(value='<div style="min-height: 0px;"></div>')

        with gr.Tab("Download Queue"):
            download_manager_html = gr.HTML(elem_id="civitai_dl_list", value='<div class="civitai_nonqueue_list"></div><div id="queue_list"></div>')
        
        def format_custom_subfolders():
            separator = '␞␞'
            try:
                with open(gl.subfolder_json, 'r') as f:
                    data = json.load(f)
                return separator.join([f"{key}{separator}{value}" for key, value in data.items()])
            except:
                return ""

        # Invisible State Components
        gr.Textbox(elem_id="custom_subfolders_list", visible=False, value=format_custom_subfolders())
        model_id = gr.Textbox(visible=False)
        queue_trigger = gr.Textbox(visible=False)
        dl_url = gr.Textbox(visible=False)
        civitai_text2img_output = gr.Textbox(visible=False)
        civitai_text2img_input = gr.Textbox(elem_id="civitai_text2img_input", visible=False)
        page_slider_trigger = gr.Textbox(elem_id="page_slider_trigger", visible=False)
        selected_model_list = gr.Textbox(elem_id="selected_model_list", visible=False)
        selected_type_list = gr.Textbox(elem_id="selected_type_list", visible=False)
        html_cancel_input = gr.Textbox(elem_id="html_cancel_input", visible=False)
        queue_html_input = gr.Textbox(elem_id="queue_html_input", visible=False)
        list_html_input = gr.Textbox(elem_id="list_html_input", visible=False)
        preview_html_input = gr.Textbox(elem_id="preview_html_input", visible=False)
        create_subfolder = gr.Textbox(elem_id="create_subfolder", visible=False)
        send_to_browser = gr.Textbox(elem_id="send_to_browser", visible=False)
        arrange_dl_id = gr.Textbox(elem_id="arrange_dl_id", visible=False)
        remove_dl_id = gr.Textbox(elem_id="remove_dl_id", visible=False)
        model_select = gr.Textbox(elem_id="model_select", visible=False)
        model_sent = gr.Textbox(elem_id="model_sent", visible=False)
        type_sent = gr.Textbox(elem_id="type_sent", visible=False)
        click_first_item = gr.Textbox(visible=False)
        empty = gr.Textbox(value="", visible=False)
        download_start = gr.Textbox(visible=False)
        download_finish = gr.Textbox(visible=False)
        tag_start = gr.Textbox(visible=False)
        tag_finish = gr.Textbox(visible=False)
        preview_start = gr.Textbox(visible=False)
        preview_finish = gr.Textbox(visible=False)
        ver_start = gr.Textbox(visible=False)
        ver_finish = gr.Textbox(visible=False)
        installed_start = gr.Textbox(visible=None)
        installed_finish = gr.Textbox(visible=None)
        organize_start = gr.Textbox(visible=None)
        organize_finish = gr.Textbox(visible=None)
        delete_finish = gr.Textbox(visible=False)
        current_model = gr.Textbox(visible=False)
        current_sha256 = gr.Textbox(visible=False)
        model_preview_html_input = gr.Textbox(visible=False)
        
        def ToggleDate(toggle_date):
            gl.sortNewest = toggle_date
        
        def select_subfolder(sub_folder):
            if sub_folder in ["None", "Only available if the selected files are of the same model type"]:
                return gr.Textbox.update(value=gl.main_folder)
            return gr.Textbox.update(value=gl.main_folder + sub_folder)

        # JS Bindings
        list_html_input.change(fn=None, inputs=hide_installed, _js="(toggleValue) => hideInstalled(toggleValue)")
        hide_installed.input(fn=None, inputs=hide_installed, _js="(toggleValue) => hideInstalled(toggleValue)")
        civitai_text2img_output.change(fn=None, inputs=civitai_text2img_output, _js="(genInfo) => genInfo_to_txt2img(genInfo)")
        download_selected.click(fn=None, _js="() => deselectAllModels()")
        select_all.click(fn=None, _js="() => selectAllModels()")
        list_models.select(fn=None, inputs=list_models, _js="(list_models) => select_model(list_models)")
        preview_html_input.change(fn=None, _js="() => adjustFilterBoxAndButtons()")
        preview_html_input.change(fn=None, _js="() => setDescriptionToggle()")
        back_to_top.click(fn=None, _js="() => BackToTop()")
        page_slider.release(fn=None, _js="() => pressRefresh()")
        
        for func in [queue_trigger, download_finish, delete_finish]:
            func.change(fn=None, inputs=current_model, _js="(modelName) => updateCard(modelName)")
        
        for comp in [list_html_input, show_nsfw]:
            comp.change(fn=None, inputs=show_nsfw, _js="(hideAndBlur) => toggleNSFWContent(hideAndBlur)")
            
        for comp in [list_html_input, size_slider]:
            comp.change(fn=None, inputs=size_slider, _js="(size) => updateCardSize(size, size * 1.5)")
            
        model_preview_html_input.change(fn=None, inputs=model_preview_html_input, _js="(html_input) => inputHTMLPreviewContent(html_input)")
        queue_html_input.change(fn=None, _js="() => setSortable()")
        click_first_item.change(fn=None, _js="() => clickFirstFigureInColumn()")
        
        # HTML Update Bindings
        queue_html_input.change(fn=HTMLChange, inputs=[queue_html_input], outputs=download_manager_html)
        list_html_input.change(fn=HTMLChange, inputs=[list_html_input], outputs=list_html)
        preview_html_input.change(fn=HTMLChange, inputs=[preview_html_input], outputs=preview_html)

        remove_dl_id.change(fn=_download.remove_from_queue, inputs=[remove_dl_id])
        arrange_dl_id.change(fn=_download.arrange_queue, inputs=[arrange_dl_id])
        html_cancel_input.change(fn=_download.download_cancel)
        html_cancel_input.change(fn=None, _js="() => cancelCurrentDl()")
        
        save_settings.click(
            fn=saveSettings,
            inputs=[
                use_search_term, content_type, period_type, sort_type, base_filter,
                create_json, toggle_date, only_liked, hide_installed, show_nsfw,
                size_slider, tile_count_slider
            ]
        )
        toggle_date.input(fn=ToggleDate, inputs=[toggle_date])
        civitai_text2img_input.change(fn=txt2img_output, inputs=civitai_text2img_input, outputs=civitai_text2img_output)
        list_html_input.change(fn=all_visible, inputs=list_html, outputs=select_all)
        
        def update_models_dropdown(input_val):
            if not gl.json_data:
                return (
                    gr.Dropdown.update(value=None, choices=[], interactive=False), # List models
                    gr.Dropdown.update(value=None, choices=[], interactive=False), # List version
                    gr.Textbox.update(value=None), # Preview HTML
                    gr.Textbox.update(value=None, interactive=False), # Trained Tags
                    gr.Textbox.update(value=None, interactive=False), # Base Model
                    gr.Textbox.update(value=None, interactive=False), # Model filename
                    gr.Textbox.update(value=None, interactive=False), # Install path
                    gr.Dropdown.update(value=None, choices=[], interactive=False), # Sub folder
                    gr.Button.update(interactive=False), # Download model btn
                    gr.Button.update(interactive=False), # Save image btn
                    gr.Button.update(interactive=False, visible=False), # Delete model btn
                    gr.Dropdown.update(value=None, choices=[], interactive=False), # File list
                    gr.Textbox.update(value=None), # DL Url
                    gr.Textbox.update(value=None), # Model ID
                    gr.Textbox.update(value=None), # Current sha256
                    gr.Button.update(interactive=False),  # Save model info
                    gr.Textbox.update(value='<div style="font-size: 24px; text-align: center; margin: 50px;">Click the search icon to load models.<br>Use the filter icon to filter results.</div>') # Model list
                )
            
            model_string = re.sub(r'\.\d{3}$', '', input_val)
            _, model_id_val = _api.extract_model_info(model_string)
            model_versions = _api.update_model_versions(model_id_val)
            (html, tags, base_mdl, DwnButton, SaveImages, DelButton, filelist, filename, dl_url_val, id_val, current_sha256_val, install_path_val, sub_folder_val) = _api.update_model_info(model_string, model_versions.get('value'))
            
            return (
                gr.Dropdown.update(value=model_string, interactive=True),
                model_versions, html, tags, base_mdl, filename, install_path_val, sub_folder_val,
                DwnButton, SaveImages, DelButton, filelist, dl_url_val, id_val, current_sha256_val,
                gr.Button.update(interactive=True),
                gr.Textbox.update()
            )
        
        model_select.change(
            fn=update_models_dropdown,
            inputs=[model_select],
            outputs=[
                list_models, list_versions, preview_html, trained_tags, base_model,
                model_filename, install_path, sub_folder, download_model, save_images,
                delete_model, file_list, dl_url, model_id, current_sha256, save_info,
                list_html_input
            ]
        )
        
        model_sent.change(fn=_file.model_from_sent, inputs=[model_sent, type_sent], outputs=[model_preview_html_input])
        send_to_browser.change(fn=_file.send_to_browser, inputs=[send_to_browser, type_sent, click_first_item], outputs=[list_html_input, get_prev_page, get_next_page, page_slider, click_first_item])
        sub_folder.select(fn=select_subfolder, inputs=[sub_folder], outputs=[install_path])

        list_versions.select(
            fn=_api.update_model_info,
            inputs=[list_models, list_versions],
            outputs=[preview_html_input, trained_tags, base_model, download_model, save_images, delete_model, file_list, model_filename, dl_url, model_id, current_sha256, install_path, sub_folder]
        )
        
        file_list.input(
            fn=_api.update_file_info,
            inputs=[list_models, list_versions, file_list],
            outputs=[model_filename, dl_url, model_id, current_sha256, download_model, delete_model, install_path, sub_folder]
        )
        
        selected_model_list.change(
            fn=show_multi_buttons,
            inputs=[selected_model_list, selected_type_list, list_versions],
            outputs=[download_selected, download_model, delete_model, save_info, save_images, subfolder_selected]
        )
        
        download_model.click(
            fn=_download.download_start,
            inputs=[download_start, dl_url, model_filename, install_path, list_models, list_versions, current_sha256, model_id, create_json, download_manager_html],
            outputs=[download_model, cancel_model, cancel_all_model, download_start, download_progress, download_manager_html]
        )
        
        download_selected.click(
            fn=_download.selected_to_queue,
            inputs=[selected_model_list, subfolder_selected, download_start, create_json, download_manager_html],
            outputs=[download_model, cancel_model, cancel_all_model, download_start, download_progress, download_manager_html]
        )
        
        for component in [download_start, queue_trigger]:
            component.change(fn=None, _js="() => setDownloadProgressBar()")
            component.change(fn=_download.download_create_thread, inputs=[download_finish, queue_trigger], outputs=[download_progress, current_model, download_finish, queue_trigger])

        download_finish.change(
            fn=_download.download_finish,
            inputs=[model_filename, list_versions, model_id],
            outputs=[download_model, cancel_model, cancel_all_model, delete_model, download_progress, list_versions]
        )
        
        cancel_model.click(_download.download_cancel)
        cancel_all_model.click(_download.download_cancel_all)
        cancel_model.click(fn=None, _js="() => cancelCurrentDl()")
        cancel_all_model.click(fn=None, _js="() => cancelAllDl()")
        
        delete_model.click(
            fn=_file.delete_model,
            inputs=[delete_finish, model_filename, list_models, list_versions, current_sha256, selected_model_list],
            outputs=[download_model, cancel_model, delete_model, delete_finish, current_model, list_versions]
        )
        
        save_info.click(fn=_file.save_model_info, inputs=[install_path, model_filename, sub_folder, current_sha256, preview_html_input], outputs=[])
        save_images.click(fn=_file.save_images, inputs=[preview_html_input, model_filename, install_path, sub_folder], outputs=[])
        
        # IO Wiring
        page_inputs = [content_type, sort_type, period_type, use_search_term, search_term, page_slider, base_filter, only_liked, show_nsfw, tile_count_slider]
        refresh_inputs = [empty if item == page_slider else item for item in page_inputs]
        page_outputs = [list_models, list_versions, list_html_input, get_prev_page, get_next_page, page_slider, save_info, save_images, download_model, delete_model, install_path, sub_folder, file_list, preview_html_input, trained_tags, base_model, model_filename]
        file_scan_inputs = [selected_tags, ver_finish, tag_finish, installed_finish, preview_finish, overwrite_toggle, tile_count_slider, skip_hash_toggle, do_html_gen]
        load_to_browser_inputs = [content_type, sort_type, period_type, use_search_term, search_term, tile_count_slider, base_filter, show_nsfw]
        
        cancel_btn_list = [cancel_all_tags, cancel_ver_search, cancel_installed, cancel_update_preview]
        browser_installed_list = page_outputs + [ver_search, save_all_tags, load_installed, update_preview] + [cancel_installed, load_to_browser_installed, installed_progress]
        browser_list = page_outputs + [ver_search, save_all_tags, load_installed, update_preview] + [cancel_ver_search, load_to_browser, version_progress]
        
        # Button Events
        for trigger, (function, use_refresh_inputs) in {
            refresh.click: (_api.initial_model_page, True),
            search_term.submit: (_api.initial_model_page, True),
            page_slider_trigger.change: (_api.initial_model_page, False),
            get_next_page.click: (_api.next_model_page, False),
            get_prev_page.click: (_api.prev_model_page, False)
        }.items():
            trigger(fn=function, inputs=refresh_inputs if use_refresh_inputs else page_inputs, outputs=page_outputs)
            trigger(fn=None, _js="() => multi_model_select()")
        
        for button in cancel_btn_list:
            button.click(fn=_file.cancel_scan)
        
        # Maintenance Tabs Wiring
        ver_search.click(fn=_file.ver_search_start, inputs=[ver_start], outputs=[ver_start, ver_search, cancel_ver_search, load_installed, save_all_tags, update_preview, organize_models, version_progress])
        ver_start.change(fn=_file.file_scan, inputs=file_scan_inputs, outputs=[version_progress, ver_finish])
        ver_finish.change(fn=_file.scan_finish, outputs=[ver_search, save_all_tags, load_installed, update_preview, organize_models, cancel_ver_search, load_to_browser])
        
        load_installed.click(fn=_file.installed_models_start, inputs=[installed_start], outputs=[installed_start, load_installed, cancel_installed, ver_search, save_all_tags, update_preview, organize_models, installed_progress])
        installed_start.change(fn=_file.file_scan, inputs=file_scan_inputs, outputs=[installed_progress, installed_finish])
        installed_finish.change(fn=_file.scan_finish, outputs=[ver_search, save_all_tags, load_installed, update_preview, organize_models, cancel_installed, load_to_browser_installed])
        
        save_all_tags.click(fn=_file.save_tag_start, inputs=[tag_start], outputs=[tag_start, save_all_tags, cancel_all_tags, load_installed, ver_search, update_preview, organize_models, tag_progress])
        tag_start.change(fn=_file.file_scan, inputs=file_scan_inputs, outputs=[tag_progress, tag_finish])
        tag_finish.change(fn=_file.save_tag_finish, outputs=[ver_search, save_all_tags, load_installed, update_preview, organize_models, cancel_all_tags])
        
        update_preview.click(fn=_file.save_preview_start, inputs=[preview_start], outputs=[preview_start, update_preview, cancel_update_preview, load_installed, ver_search, save_all_tags, organize_models, preview_progress])
        preview_start.change(fn=_file.file_scan, inputs=file_scan_inputs, outputs=[preview_progress, preview_finish])
        preview_finish.change(fn=_file.save_preview_finish, outputs=[ver_search, save_all_tags, load_installed, update_preview, organize_models, cancel_update_preview])
        
        organize_models.click(fn=_file.organize_start, inputs=[organize_start], outputs=[organize_start, organize_models, cancel_organize, load_installed, ver_search, save_all_tags, update_preview, organize_progress])
        organize_start.change(fn=_file.file_scan, inputs=file_scan_inputs, outputs=[organize_progress, organize_finish])
        organize_finish.change(fn=_file.save_preview_finish, outputs=[ver_search, save_all_tags, load_installed, update_preview, organize_models, cancel_update_preview])
        
        load_to_browser_installed.click(fn=_file.load_to_browser, inputs=load_to_browser_inputs, outputs=browser_installed_list)
        load_to_browser.click(fn=_file.load_to_browser, inputs=load_to_browser_inputs, outputs=browser_list)
        create_subfolder.change(fn=_file.updateSubfolder, inputs=create_subfolder, outputs=[])

    tab_name = "CivitAI Browser+"
    return (civitai_interface, tab_name, "civitai_interface"),

def subfolder_list(folder, desc=None):
    if folder is None:
        return
    model_folder = _api.contenttype_folder(folder, desc)
    return _file.getSubfolders(model_folder)

def make_lambda(folder, desc):
    return lambda: {"choices": subfolder_list(folder, desc)}

def on_ui_settings():
    cat_id = "civitai_browser_plus"
    section = (cat_id, "CivitAI Browser+")
    
    if ver_bool:
        from modules.options import categories
        categories.register_category(cat_id, "CivitAI Browser+")
    
    # Helper for adding options
    def add_opt(name, default, label, info_text=None, component=None, component_args=None, **kwargs):
        args = {}
        if component:
            args['component'] = component
        if component_args:
            args['component_args'] = component_args
            
        opt = shared.OptionInfo(
            default,
            label,
            section=section,
            **({'category_id': cat_id} if ver_bool else {}),
            **args,
            **kwargs
        )
        if info_text and hasattr(opt, 'info'):
            opt.info(info_text)
        shared.opts.add_option(name, opt)

    add_opt("use_aria2", True, "Download models using Aria2", "Disable if experiencing issues or using proxy")
    add_opt("disable_dns", False, "Disable Async DNS for Aria2", "Useful for PortMaster/DNS software")
    add_opt("show_log", False, "Show Aria2 logs in console", "Requires UI reload")
    add_opt("split_aria2", 64, "Aria2 Connections", "Max 64", component=gr.Slider, component_args={"minimum": 1, "maximum": 64, "step": 1})
    add_opt("aria2_flags", "", "Custom Aria2 flags", "Requires UI reload")
    add_opt("unpack_zip", False, "Auto unpack .zip files")
    add_opt("save_api_info", False, "Save API info JSON")
    add_opt("auto_save_all_img", False, "Auto save all images")
    add_opt("custom_api_key", "", "Personal CivitAI API key", "Requires UI reload")
    add_opt("hide_early_access", True, "Hide early access models")
    add_opt("use_LORA", ver_bool, "Combine LoCon, LORA & DoRA")
    add_opt("dot_subfolders", True, "Hide '.' folders")
    add_opt("use_local_html", False, "Use local HTML for info")
    add_opt("local_path_in_html", False, "Use local images in HTML")
    add_opt("page_header", False, "Fixed page header", "Requires UI reload")
    add_opt("video_playback", True, "Enable Gif/Video playback", "Disable for CPU performance")
    add_opt("individual_meta_btn", True, "Individual prompt buttons")
    add_opt("model_desc_to_json", True, "Save model description to JSON")
    add_opt("civitai_not_found_print", True, "Show 'Model not found' errors")
    add_opt("civitai_send_to_browser", False, "Send to browser button action")
    add_opt("image_location", "", "Custom images path")
    add_opt("sub_image_location", True, "Use subfolders in custom path")
    add_opt("save_to_custom", False, "Save HTML/Info to custom path")
    add_opt("custom_civitai_proxy", "", "Proxy address", "socks4/5 supported")
    add_opt("cabundle_path_proxy", "", "Custom CA Bundle path")
    add_opt("disable_sll_proxy", False, "Disable SSL checks")

    # Dynamic Subfolder Options
    use_LORA = getattr(opts, "use_LORA", False)
    folders = [
        "Checkpoint",
        "LORA, LoCon, DoRA" if use_LORA else "LORA",
        "LoCon" if not use_LORA else None,
        "DoRA" if not use_LORA else None,
        "TextualInversion", "Poses", "Controlnet", "Hypernetwork", "MotionModule",
        ("Upscaler", "SWINIR"), ("Upscaler", "REALESRGAN"), ("Upscaler", "GFPGAN"),
        ("Upscaler", "BSRGAN"), ("Upscaler", "ESRGAN"),
        "VAE", "AestheticGradient", "Wildcards", "Workflows", "Other"
    ]

    for folder in folders:
        if not folder: continue
        
        if isinstance(folder, tuple):
            name, desc = folder
            setting_name = f"{desc}_upscale"
            label = f"{name} - {desc}"
        else:
            name = desc = folder
            setting_name = folder
            label = folder
            
        if folder == "LORA, LoCon, DoRA":
            name = "LORA"
            setting_name = "LORA_LoCon"
            
        add_opt(f"{setting_name}_default_subfolder", "None", label, component=gr.Dropdown, component_args=make_lambda(name, desc))

script_callbacks.on_ui_tabs(on_ui_tabs)
script_callbacks.on_ui_settings(on_ui_settings)