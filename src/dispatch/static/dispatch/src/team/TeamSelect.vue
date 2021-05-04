<template>
  <v-combobox
    v-model="team"
    prepend-icon="people"
    :items="items"
    item-text="code"
    :search-input.sync="search"
    :menu-props="{ maxHeight: '400' }"
    :label="label"
    :loading="loading"
    @update:search-input="fetchData({ q: $event })"
  >
    <template v-slot:no-data>
      <v-list-item>
        <v-list-item-content>
          <v-list-item-title>
            No Teams matching "
            <strong>{{ search }}</strong
            >".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import TeamApi from "@/team/api";
import { cloneDeep } from "lodash";
export default {
  name: "TeamSelect",
  props: {
    value: {
      type: Object,
      default: function() {
        return {};
      }
    },
    label: {
      type: String,
      default: function() {
        return "Team";
      }
    }
  },

  data() {
    return {
      loading: false,
      items: [],
      search: null
    };
  },

  computed: {
    team: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      }
    }
  },

  created() {
    this.fetchData({});
  },

  methods: {
    fetchData(filterOptions) {
      this.error = null;
      this.loading = true;
      TeamApi.getAll(filterOptions).then(response => {
        this.items = response.data.items;
        this.loading = false;
      });
    }
  }
};
</script>
