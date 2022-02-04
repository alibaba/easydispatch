<template>
  <ValidationProvider :rules="rules" immediate>
    <v-autocomplete
      v-model="service"
      :items="items"
      :search-input.sync="search"
      :menu-props="{ maxHeight: '400' }"
      cache-items
      item-text="code"
      label="Service"
      placeholder="Start typing to Search"
      return-object
      slot-scope="{ errors, valid }"
      :error-messages="errors"
      :success="valid"
      :loading="loading"
      hint="A Service for your team."
      message="This field is required"
      required
    />
  </ValidationProvider>
</template>

<script>
import ServiceApi from "@/service/api";
import { cloneDeep } from "lodash";
import { ValidationProvider } from "vee-validate";
export default {
  name: "ServiceSelect",

  props: {
    rules: [String],
    value: {
      type: Object,
      default: function () {
        return {};
      },
    },
  },
  components: {
    ValidationProvider,
  },
  data() {
    return {
      loading: false,
      search: null,
      select: null,
      items: [],
    };
  },

  watch: {
    search(val) {
      val && val !== this.select && this.querySelections(val);
    },
    value(val) {
      if (!val) return;
      this.items.push(val);
    },
  },

  computed: {
    service: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },

  methods: {
    querySelections(v) {
      this.loading = true;
      // Simulated ajax query
      ServiceApi.getAll({ q: v }).then((response) => {
        this.items = response.data.items;
        this.loading = false;
      });
    },
  },

  mounted() {
    this.error = null;
    this.loading = true;
    ServiceApi.getAll().then((response) => {
      this.items = response.data.items;
      this.loading = false;
    });
  },
};
</script>
