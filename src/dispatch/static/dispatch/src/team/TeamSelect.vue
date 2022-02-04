<template>
  <ValidationProvider :rules="rules" immediate>
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
      slot-scope="{ errors, valid }"
      :error-messages="errors"
      :success="valid"
      hint="select a team."
      message="This field is required"
      required
    >
      <template v-slot:no-data>
        <v-list-item>
          <v-list-item-content>
            <v-list-item-title>
              No Teams matching "
              <strong>{{ search }}</strong>".
            </v-list-item-title>
          </v-list-item-content>
        </v-list-item>
      </template>
    </v-combobox>
  </ValidationProvider>
</template>

<script>
import TeamApi from "@/team/api";
import { cloneDeep, debounce } from "lodash";
import { ValidationProvider } from "vee-validate";
export default {
  name: "TeamSelect",
  props: {
    rules: [String],
    value: {
      type: Object,
      default: function () {
        return {};
      },
    },
    label: {
      type: String,
      default: function () {
        return "Team";
      },
    },
  },

  components: {
    ValidationProvider,
  },
  data() {
    return {
      loading: false,
      items: [],
      search: null,
    };
  },

  computed: {
    team: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },
  created() {
    this.fetchData({});
  },

  methods: {
    fetchData(filterOptions) {
      this.error = null;
      this.loading = true;
      TeamApi.getAll(filterOptions).then((response) => {
        this.items = response.data.items;
        this.loading = false;
      });
    },
  },
};
</script>
