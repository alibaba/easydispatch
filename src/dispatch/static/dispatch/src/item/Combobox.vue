<template>
  <ValidationProvider :rules="rules" immediate>
    <v-combobox
      v-model="datas"
      :items="items"
      item-text="code"
      :search-input.sync="search"
      hide-selected
      :label="label"
      :loading="loading"
      @update:search-input="getFilteredData({ q: $event })"
      slot-scope="{ errors, valid }"
      :error-messages="errors"
      :success="valid"
      hint="select a item."
      message="This field is required"
      required
    >
      <template v-slot:no-data>
        <v-list-item>
          <v-list-item-content>
            <v-list-item-title>
              No Item matching "
              <strong>{{ search }}</strong>"
            </v-list-item-title>
          </v-list-item-content>
        </v-list-item>
      </template>
      <template v-slot:append-item>
        <v-list-item v-if="more" @click="loadMore()">
          <v-list-item-content>
            <v-list-item-subtitle>Load More</v-list-item-subtitle>
          </v-list-item-content>
        </v-list-item>
      </template>
    </v-combobox>
  </ValidationProvider>
</template>

<script>
import ItemApi from "@/item/api";
import { cloneDeep, debounce } from "lodash";
import { ValidationProvider } from "vee-validate";
export default {
  name: "ItemCombobox",
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
      defualt: "",
    },
  },
  components: {
    ValidationProvider,
  },
  data() {
    return {
      loading: false,
      items: [],
      more: false,
      numItems: 5,
      search: null,
    };
  },

  computed: {
    datas: {
      get() {
        return cloneDeep(this.value);
      },
      set(value) {
        if (typeof value === "string") {
          let v = {
            slug: value,
          };
          this.items.push(v);
        }
        this.$emit("input", value);
      },
    },
  },

  created() {
    this.fetchData({});
  },

  methods: {
    loadMore() {
      this.numItems = this.numItems + 5;
      this.getFilteredData({ q: this.search, itemsPerPage: this.numItems });
    },
    fetchData(filterOptions) {
      this.error = null;
      this.loading = true;
      ItemApi.getAll(filterOptions).then((response) => {
        this.items = response.data.items;
        this.total = response.data.total;

        if (this.items.length < this.total) {
          this.more = true;
        } else {
          this.more = false;
        }

        this.loading = false;
      });
    },
    getFilteredData: debounce(function (options) {
      this.fetchData(options);
    }, 500),
  },
};
</script>
