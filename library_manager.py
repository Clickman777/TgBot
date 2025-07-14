import os
import json
from GetNovel.models import Novel

class LibraryManager:
    USER_LIBRARIES_FILE = "user_libraries.json"

    def load_libraries(self):
        if not os.path.exists(self.USER_LIBRARIES_FILE):
            return {}
        try:
            with open(self.USER_LIBRARIES_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def save_libraries(self, libraries):
        with open(self.USER_LIBRARIES_FILE, 'w') as f:
            json.dump(libraries, f, indent=4)

    def add_to_library(self, user_id, novel_info: Novel):
        user_id = str(user_id)
        libraries = self.load_libraries()
        if user_id not in libraries:
            libraries[user_id] = []
        if not any(n['url'] == novel_info.url for n in libraries[user_id]):
            libraries[user_id].append({
                "title": novel_info.title, "url": novel_info.url,
                "author": novel_info.author, "cover_url": novel_info.cover_url,
                "genres": novel_info.genres, "description": novel_info.description
            })
            self.save_libraries(libraries)
            return True
        return False

    def remove_from_library(self, user_id: int, index: int):
        user_id = str(user_id)
        libraries = self.load_libraries()
        user_library = libraries.get(user_id, [])
        
        if 0 <= index < len(user_library):
            removed_novel = user_library.pop(index)
            libraries[user_id] = user_library
            self.save_libraries(libraries)
            return removed_novel
        return None