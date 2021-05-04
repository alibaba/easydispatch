<template>
  <v-combobox
    v-model="location"
    prepend-icon="person"
    :items="items"
    item-text="location_code"
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
            No Locations matching "
            <strong>{{ search }}</strong
            >".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import LocationApi from "@/location/api";
import { cloneDeep } from "lodash";
export default {
  name: "LocationSelect",
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
        return "Location";
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
    location: {
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
      LocationApi.getAll(filterOptions).then(response => {
        this.items = response.data.items;
        this.loading = false;
      });
    }
  }
};
</script>
