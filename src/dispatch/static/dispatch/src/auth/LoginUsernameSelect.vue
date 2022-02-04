<template>
  <v-combobox
    v-model="auth"
    prepend-icon="account_box"
    :items="items"
    item-text="email"
    :search-input.sync="search"
    :menu-props="{ maxHeight: '400' }"
    :label="label"
    :loading="loading" 
  >
    <template v-slot:no-data>
      <v-list-item>
        <v-list-item-content>
          <v-list-item-title>
            No Matching Usernamess"
            <strong>{{ search }}</strong>".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import { cloneDeep } from "lodash";
import { mapActions } from "vuex";
import { mapFields } from "vuex-map-fields";
export default {
  name: "LoginUsernameSelect",
  props: {
    value: {
      type: Object,
      default: function () {
        return {};
      },
    },
    label: {
      type: String,
      default: function () {
        return "Login Username";
      },
    },
  },

  data() {
    return {
      search: null,
    };
  },

  computed: {
    ...mapFields("auth", ["table.loading", "table.rows.items"]),
    auth: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },

  mounted() {
    this.getAll();
  },

  methods: {
    ...mapActions("auth", ["getAll"]),
  },
};
</script>
