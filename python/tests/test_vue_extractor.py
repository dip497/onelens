"""Vue extractor — Component/HttpCall extraction from SFC text + import edges."""

from onelens.extractors.vue_extractor import extract_vue_source, extract_dir


USER_LIST = """
<template>
  <div>
    <UserDetail v-for="u in users" :user="u" />
  </div>
</template>

<script setup>
import axios from 'axios'
import UserDetail from './UserDetail.vue'

const users = ref([])

async function load() {
  const res = await axios.get('/api/users')
  users.value = res.data
}

async function remove(id) {
  await axios.delete(`/api/users/${id}`)
}

async function patchName(id, name) {
  // axios.post('/should/not/be/extracted')  <- commented out
  await axios.patch(`/api/users/${id}`, { name })
}

function search(term) {
  return fetch(`/api/search?q=${term}`, { method: 'POST' })
}
</script>
"""


def test_component_node():
    vf = extract_vue_source("views/UserList.vue", USER_LIST)
    assert vf.component["fqn"] == "views/UserList.vue"
    assert vf.component["name"] == "UserList"
    assert vf.component["lang"] == "vue"


def test_http_calls_method_and_path():
    vf = extract_vue_source("views/UserList.vue", USER_LIST)
    pairs = {(c["httpMethod"], c["path"]) for c in vf.http_calls}
    assert ("GET", "/api/users") in pairs
    assert ("DELETE", "`/api/users/${id}`".strip("`")) in pairs or \
           ("DELETE", "/api/users/${id}") in pairs
    assert ("PATCH", "/api/users/${id}") in pairs
    assert ("POST", "/api/search?q=${term}") in pairs


def test_commented_call_not_extracted():
    vf = extract_vue_source("views/UserList.vue", USER_LIST)
    assert all("should/not/be/extracted" not in c["path"] for c in vf.http_calls)


def test_each_call_owned_by_component():
    vf = extract_vue_source("views/UserList.vue", USER_LIST)
    assert vf.http_calls, "expected at least one http call"
    assert all(c["componentFqn"] == "views/UserList.vue" for c in vf.http_calls)


def test_axios_config_form():
    src = """
    <script>
    export default {
      methods: {
        save() { return axios({ method: 'put', url: '/api/save' }) }
      }
    }
    </script>
    """
    vf = extract_vue_source("Save.vue", src)
    assert ("PUT", "/api/save") in {(c["httpMethod"], c["path"]) for c in vf.http_calls}


def test_extract_dir_resolves_uses_component(tmp_path):
    (tmp_path / "views").mkdir()
    (tmp_path / "views" / "UserList.vue").write_text(USER_LIST, encoding="utf-8")
    (tmp_path / "views" / "UserDetail.vue").write_text(
        "<template><span>{{ user.name }}</span></template>", encoding="utf-8"
    )
    data = extract_dir(tmp_path)

    assert data["header"]["lang"] == "vue"
    names = {c["name"] for c in data["components"]}
    assert {"UserList", "UserDetail"} <= names
    # UserList imports ./UserDetail.vue → a USES_COMPONENT edge resolves.
    edges = {(e["src"], e["dst"]) for e in data["componentEdges"]}
    assert ("views/UserList.vue", "views/UserDetail.vue") in edges
