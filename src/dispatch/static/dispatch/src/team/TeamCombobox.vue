<template>
  <v-combobox
    v-model="team"
    prepend-icon="people"
    :items="items"
    item-text="code"
    :search-input.sync="search"
    :menu-props="{ maxHeight: '400' ,closeOnClick: true, closeOnContentClick: true,}"
    hide-selected
    :label="label"
    multiple
    close
    chips
    clearable
    :loading="loading" 
    dense
  >
    <template v-slot:no-data>
      <v-list-item>
        <v-list-item-content>
          <v-list-item-title>
            No Indivduals matching "
            <strong>{{ search }}</strong>".
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script>
import TeamApi from "@/team/api";
import { cloneDeep, debounce } from "lodash";
export default {
  name: "TeamCombo",
  props: {
    value: {
      type: Array,
      default: function () {
        return [];
      },
    },
    label: {
      type: String,
      default: function () {
        return "Team";
      },
    },
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
        this._teams = value.map((v) => {
          if (typeof v === "string") {
            v = {
              code: v,
            };
            this.items.push(v);
          }
          return v;
        });
        this.$emit(
          "input",
          this._teams.filter((row) => row.code != undefined)
        );
      },
    },
  },

  created() {
    this.fetchData( );
  },

  methods: {
    fetchData: debounce(function ( ) {
      this.error = null;
      this.loading = true;
      TeamApi.getAll( ).then((response) => {
        this.items = response.data.items;
        this.loading = false;
      });
    }, 200),
  },
};
</script>
